"use client";

import { useEffect, useRef } from "react";
import Image from "next/image";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ActionPlanCard } from "@/components/chat/action-plan-card";
import { DowntimeCard } from "@/components/chat/downtime-card";
import { MarkdownMessage } from "@/components/chat/markdown-message";
import { PredictionCard } from "@/components/chat/prediction-card";
import { ShapCard } from "@/components/chat/shap-card";
import type { WomaiMessage } from "@/lib/types";

interface ChatMessagesProps {
  messages: WomaiMessage[];
  status: "submitted" | "streaming" | "ready" | "error";
  agentStatus: string | null;
  checkedSteps: Record<string, boolean>;
  onToggleStep: (stepId: string) => void;
  error: Error | undefined;
  onRetry: () => void;
}

export function ChatMessages({
  messages,
  status,
  agentStatus,
  checkedSteps,
  onToggleStep,
  error,
  onRetry,
}: ChatMessagesProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status, agentStatus]);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-16 text-center">
            <div className="relative size-12 overflow-hidden rounded-xl shadow-sm border border-slate-100 bg-slate-50">
              <Image
                src="/images/logo_icon.png"
                alt="WO.M.AI Logo"
                fill
                sizes="48px"
                className="object-cover"
              />
            </div>
            <h2 className="text-lg font-semibold">
              Ceritakan kondisi mesinmu
            </h2>
            <p className="max-w-md text-sm text-muted-foreground">
              {
                "Contoh: “motor line 3 suhu prosesnya 310K, torsi 45 Nm, sudah dipakai 200 menit sejak ganti tool”"
              }
            </p>
          </div>
        )}

        {messages.map((message) =>
          message.role === "user" ? (
            <div key={message.id} className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl bg-primary px-4 py-2 text-sm whitespace-pre-wrap text-primary-foreground">
                {message.parts
                  .filter((p) => p.type === "text")
                  .map((p) => p.text)
                  .join("")}
              </div>
            </div>
          ) : (
            <div key={message.id} className="flex flex-col gap-3">
              {message.parts.map((part, i) => {
                switch (part.type) {
                  case "text":
                    return <MarkdownMessage key={i} content={part.text} />;
                  case "data-prediction":
                    return <PredictionCard key={i} data={part.data} />;
                  case "data-shap":
                    return <ShapCard key={i} data={part.data} />;
                  case "data-downtime":
                    return <DowntimeCard key={i} data={part.data} />;
                  case "data-sop":
                    return (
                      <ActionPlanCard
                        key={i}
                        plan={part.data}
                        checkedSteps={checkedSteps}
                        onToggleStep={onToggleStep}
                      />
                    );
                  default:
                    return null;
                }
              })}
            </div>
          ),
        )}

        {(status === "submitted" || status === "streaming") && agentStatus && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            {agentStatus}
          </div>
        )}

        {error && (
          <div className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
            <span>Terjadi kesalahan saat memproses. Coba lagi.</span>
            <Button variant="outline" size="sm" onClick={onRetry}>
              Coba lagi
            </Button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
