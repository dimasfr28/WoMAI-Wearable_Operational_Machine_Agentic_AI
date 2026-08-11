"use client";

import { useState } from "react";
import { SendHorizonal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MachinePicker } from "@/components/chat/machine-picker";
import { ManualInputDialog } from "@/components/chat/manual-input-dialog";
import type { Machine } from "@/lib/types";

const MAX_LENGTH = 2000;

interface ChatInputProps {
  disabled: boolean;
  onSend: (text: string) => void;
  machine: Machine | null;
  onMachineChange: (m: Machine | null) => void;
}

export function ChatInput({
  disabled,
  onSend,
  machine,
  onMachineChange,
}: ChatInputProps) {
  const [input, setInput] = useState("");

  function submit() {
    const text = input.trim();
    if (!text || disabled) return;
    onSend(text);
    setInput("");
  }

  return (
    <div className="border-t bg-background p-4">
      <form
        className="mx-auto flex w-full max-w-3xl items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <MachinePicker
          value={machine}
          onChange={onMachineChange}
          disabled={disabled}
        />
        <ManualInputDialog
          disabled={disabled}
          onSend={onSend}
          defaultType={machine?.type}
        />
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          maxLength={MAX_LENGTH}
          rows={2}
          placeholder={
            "Ketik kondisi mesin, mis. “motor line 3 suhu prosesnya 310K, torsi 45 Nm…”"
          }
          className="min-h-0 resize-none"
        />
        <Button type="submit" size="icon" disabled={disabled || !input.trim()}>
          <SendHorizonal className="size-4" />
          <span className="sr-only">Kirim</span>
        </Button>
      </form>
    </div>
  );
}
