"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Chat } from "@/components/chat/chat";
import { RequireActiveMachine } from "@/components/require-active-machine";
import { getSession } from "@/lib/storage";
import type { ChatSession } from "@/lib/types";

export default function ChatSessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  // Track id alongside the result so navigating A->B resets to undefined
  // before the effect fires (avoids rendering B with A's messages)
  const [entry, setEntry] = useState<{
    id: string;
    session: ChatSession | null | undefined;
  }>({ id, session: undefined });

  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEntry({ id, session: undefined });
    getSession(id).then((session) => {
      if (active) setEntry({ id, session: session ?? null });
    });
    return () => {
      active = false;
    };
  }, [id]);

  // If state hasn't caught up to the new id yet, treat as loading
  const session = entry.id === id ? entry.session : undefined;

  if (session === undefined) return null; // menunggu data
  if (session === null) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2">
        <p className="text-muted-foreground">Sesi tidak ditemukan.</p>
        <Link className="text-primary underline" href="/chat">
          Mulai chat baru
        </Link>
      </div>
    );
  }

  return (
    <RequireActiveMachine>
      {(machine) => (
        <Chat
          key={id}
          sessionId={id}
          initialMessages={session.messages}
          initialCheckedSteps={session.checkedSteps}
          initialCreatedAt={session.createdAt}
          machine={machine}
        />
      )}
    </RequireActiveMachine>
  );
}
