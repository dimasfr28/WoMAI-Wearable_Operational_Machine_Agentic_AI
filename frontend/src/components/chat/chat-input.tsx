"use client";

import Link from "next/link";
import { useState } from "react";
import { SendHorizonal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Machine } from "@/lib/types";

const MAX_LENGTH = 2000;

interface ChatInputProps {
  disabled: boolean;
  onSend: (text: string) => void;
  machine: Machine;
}

export function ChatInput({ disabled, onSend, machine }: ChatInputProps) {
  const [input, setInput] = useState("");

  function submit() {
    const text = input.trim();
    if (!text || disabled) return;
    onSend(text);
    setInput("");
  }

  return (
    <div className="border-t bg-background p-4">
      <div className="mx-auto mb-2 flex w-full max-w-3xl justify-end">
        <Button
          variant="ghost"
          size="sm"
          className="h-auto p-0 text-xs text-muted-foreground hover:text-foreground"
          render={<Link href="/machine-report" />}
        >
          Lihat laporan lengkap →
        </Button>
      </div>
      <form
        className="mx-auto flex w-full max-w-3xl items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
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
          placeholder={`Tanyakan sesuatu tentang ${machine.name}…`}
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
