"use server";

import { requireSession } from "@/lib/auth/session";
import type { ChatSession } from "@/lib/types";

// Data contoh in-memory — lihat catatan yang sama di actions/machines.ts.
// Kosong di awal: riwayat percakapan wajar dimulai kosong untuk user baru.
let sessionsStore: ChatSession[] = [];

export async function loadSessionsAction(): Promise<ChatSession[]> {
  await requireSession();
  return sessionsStore;
}

export async function getSessionAction(
  id: string,
): Promise<ChatSession | null> {
  await requireSession();
  return sessionsStore.find((s) => s.id === id) ?? null;
}

export async function saveSessionAction(session: ChatSession): Promise<void> {
  await requireSession();
  const idx = sessionsStore.findIndex((s) => s.id === session.id);
  if (idx >= 0) {
    sessionsStore = [
      ...sessionsStore.slice(0, idx),
      session,
      ...sessionsStore.slice(idx + 1),
    ];
  } else {
    sessionsStore = [...sessionsStore, session];
  }
}

export async function deleteSessionAction(id: string): Promise<void> {
  await requireSession();
  sessionsStore = sessionsStore.filter((s) => s.id !== id);
}

export async function clearSessionsAction(): Promise<void> {
  await requireSession();
  sessionsStore = [];
}
