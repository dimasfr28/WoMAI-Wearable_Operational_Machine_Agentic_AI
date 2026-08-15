"use client";

import { useState } from "react";
import { Chat } from "@/components/chat/chat";
import { RequireActiveMachine } from "@/components/require-active-machine";

export default function NewChatPage() {
  const [id] = useState(() => crypto.randomUUID());
  return (
    <RequireActiveMachine>
      {(machine) => (
        <Chat sessionId={id} initialMessages={[]} machine={machine} />
      )}
    </RequireActiveMachine>
  );
}
