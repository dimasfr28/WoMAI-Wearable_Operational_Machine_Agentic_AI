"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { ChatInput } from "@/components/chat/chat-input";
import { ChatMessages } from "@/components/chat/chat-messages";
import { getMachine, MACHINES_CHANGED_EVENT } from "@/lib/machines";
import { deriveTitle, saveSession } from "@/lib/storage";
import type { Machine, PredictionResult, WomaiMessage } from "@/lib/types";

interface ChatProps {
  sessionId: string;
  initialMessages: WomaiMessage[];
  initialCheckedSteps?: Record<string, boolean>;
  initialCreatedAt?: string;
  initialMachine?: Machine | null;
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
  initialMachine,
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

  const [machine, setMachine] = useState<Machine | null>(initialMachine ?? null);
  const machineRef = useRef(machine);
  // Keep machineRef in sync after every render so persist always reads the latest value
  useEffect(() => {
    machineRef.current = machine;
  });

  // Rename mesin menyebar ke picker sesi yang sedang terbuka; mesin terhapus
  // mempertahankan snapshot terakhir
  useEffect(() => {
    const refresh = () => {
      const cur = machineRef.current;
      if (!cur) return;
      getMachine(cur.id)
        .then((m) => {
          if (m) setMachine(m);
        })
        .catch(() => {
          // biarkan snapshot terakhir bila gagal memuat
        });
    };
    window.addEventListener(MACHINES_CHANGED_EVENT, refresh);
    return () => window.removeEventListener(MACHINES_CHANGED_EVENT, refresh);
  }, []);

  const createdAtRef = useRef(initialCreatedAt ?? new Date().toISOString());
  const urlUpdatedRef = useRef(false);
  const pathname = usePathname();

  const { messages, sendMessage, status, error, regenerate } =
    useChat<WomaiMessage>({
      id: sessionId,
      messages: initialMessages,
      transport: new DefaultChatTransport({ api: "/api/chat" }),
      onData: (part) => {
        if (part.type === "data-status") setAgentStatus(part.data.message);
      },
    });

  function persist(
    msgs: WomaiMessage[],
    checked: Record<string, boolean>,
  ) {
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
      machineId: machineRef.current?.id,
      machineName: machineRef.current?.name,
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

  function handleMachineChange(m: Machine | null) {
    // Sync ref eagerly so persist reads the new value immediately
    machineRef.current = m;
    setMachine(m);
    // Persist immediately when user changes machine mid-session
    if (messages.length > 0) {
      persist(messages, checkedStepsRef.current);
    }
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
        onMachineChange={handleMachineChange}
      />
    </div>
  );
}
