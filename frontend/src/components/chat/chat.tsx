"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { ChatInput } from "@/components/chat/chat-input";
import { ChatMessages } from "@/components/chat/chat-messages";
import { deriveTitle, saveSession } from "@/lib/storage";
import type { Machine, PredictionResult, WomaiMessage } from "@/lib/types";

interface ChatProps {
  sessionId: string;
  initialMessages: WomaiMessage[];
  initialCheckedSteps?: Record<string, boolean>;
  initialCreatedAt?: string;
  machine: Machine;
}

function firstUserText(messages: WomaiMessage[]): string {
  const first = messages.find((m) => m.role === "user");
  if (!first) return "";
  return first.parts
    .filter((p) => p.type === "text")
    .map((p) => p.text)
    .join(" ");
}

function lastPredictionOf(
  messages: WomaiMessage[],
): PredictionResult | undefined {
  for (const message of [...messages].reverse()) {
    if (message.role !== "assistant") continue;
    for (const part of message.parts) {
      if (part.type === "data-prediction") return part.data;
    }
  }
  return undefined;
}

export function Chat({
  sessionId,
  initialMessages,
  initialCheckedSteps,
  initialCreatedAt,
  machine,
}: ChatProps) {
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [checkedSteps, setCheckedSteps] = useState<Record<string, boolean>>(
    initialCheckedSteps ?? {},
  );
  const checkedStepsRef = useRef(checkedSteps);
  // Keep ref in sync after every render so the save effect always reads the latest value
  useEffect(() => {
    checkedStepsRef.current = checkedSteps;
  });

  const createdAtRef = useRef(initialCreatedAt ?? new Date().toISOString());
  const urlUpdatedRef = useRef(false);
  const pathname = usePathname();

  const { messages, sendMessage, status, error, regenerate } =
    useChat<WomaiMessage>({
      id: sessionId,
      messages: initialMessages,
      transport: new DefaultChatTransport({
        api: "/api/chat",
        // machineId dikirim di setiap request supaya backend tidak perlu
        // menebak/menanyakan mesin dari isi pesan (rancangan.txt Section 8)
        // — mesin sudah dipilih secara global sebelum masuk chat.
        body: { machineId: machine.id },
      }),
      onData: (part) => {
        if (part.type === "data-status") setAgentStatus(part.data.message);
      },
    });

  function persist(msgs: WomaiMessage[], checked: Record<string, boolean>) {
    const cleanMessages = msgs.map((m) => ({
      ...m,
      parts: m.parts.filter((p) => p.type !== "step-start"),
    }));
    void saveSession({
      id: sessionId,
      title: deriveTitle(firstUserText(msgs)),
      createdAt: createdAtRef.current,
      updatedAt: new Date().toISOString(),
      messages: cleanMessages,
      lastPrediction: lastPredictionOf(msgs),
      checkedSteps: checked,
      machineId: machine.id,
      machineName: machine.name,
    }).catch(() => {
      // Simpan gagal (mis. offline) — sesi tetap tampil di layar
    });
    if (!urlUpdatedRef.current && pathname === "/chat") {
      window.history.replaceState(null, "", `/chat/${sessionId}`);
      urlUpdatedRef.current = true;
    }
  }

  // Simpan sesi setiap respons selesai
  useEffect(() => {
    if (status !== "ready" || messages.length === 0) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAgentStatus(null);
    persist(messages, checkedStepsRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, messages]);

  function toggleStep(stepId: string) {
    const next = { ...checkedSteps, [stepId]: !checkedSteps[stepId] };
    persist(messages, next);
    setCheckedSteps(next);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ChatMessages
        messages={messages}
        status={status}
        agentStatus={agentStatus}
        checkedSteps={checkedSteps}
        onToggleStep={toggleStep}
        error={error}
        onRetry={() => regenerate()}
      />
      <ChatInput
        disabled={status === "submitted" || status === "streaming"}
        onSend={(text) => sendMessage({ text })}
        machine={machine}
      />
    </div>
  );
}
