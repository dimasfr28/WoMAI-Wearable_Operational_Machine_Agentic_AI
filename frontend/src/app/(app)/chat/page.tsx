"use client";

import { useState } from "react";
import { Chat } from "@/components/chat/chat";

export default function NewChatPage() {
  const [id] = useState(() => crypto.randomUUID());
  return <Chat sessionId={id} initialMessages={[]} />;
}
