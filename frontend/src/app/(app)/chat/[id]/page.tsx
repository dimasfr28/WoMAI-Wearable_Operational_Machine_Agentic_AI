"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Chat } from "@/components/chat/chat";
import { getMachine } from "@/lib/machines";
import { getSession } from "@/lib/storage";
import type { ChatSession, Machine } from "@/lib/types";

type Loaded = {
  session: ChatSession;
  machine: Machine | null;
};

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
    data: Loaded | null | undefined;
  }>({ id, data: undefined });

  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEntry({ id, data: undefined });
    (async () => {
      const session = await getSession(id);
      if (!active) return;
      if (!session) {
        setEntry({ id, data: null });
        return;
      }
      const machine: Machine | null = session.machineId
        ? ((await getMachine(session.machineId)) ?? {
            id: session.machineId,
            name: session.machineName ?? "Mesin terhapus",
            type: "M" as const,
            createdAt: session.createdAt,
          })
        : null;
      if (!active) return;
      setEntry({ id, data: { session, machine } });
    })();
    return () => {
      active = false;
    };
  }, [id]);

  // If state hasn't caught up to the new id yet, treat as loading
  const data = entry.id === id ? entry.data : undefined;

  if (data === undefined) return null; // menunggu data
  if (data === null) {
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
    <Chat
      key={id}
      sessionId={id}
      initialMessages={data.session.messages}
      initialCheckedSteps={data.session.checkedSteps}
      initialCreatedAt={data.session.createdAt}
      initialMachine={data.machine}
    />
  );
}
