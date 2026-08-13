import {
  clearSessionsAction,
  deleteSessionAction,
  getSessionAction,
  loadSessionsAction,
  saveSessionAction,
} from "@/app/actions/sessions";
import type { ChatSession } from "@/lib/types";

// Re-export helper murni agar call-site lama (mis. chat.tsx) tetap jalan.
export { deriveTitle } from "@/lib/title";

// Dipertahankan agar komponen bisa memicu re-fetch setelah mutasi.
export const SESSIONS_CHANGED_EVENT = "womai:sessions-changed";

function notify(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SESSIONS_CHANGED_EVENT));
  }
}

export async function loadSessions(): Promise<ChatSession[]> {
  return loadSessionsAction();
}

export async function getSession(
  id: string,
): Promise<ChatSession | null> {
  return getSessionAction(id);
}

export async function saveSession(session: ChatSession): Promise<void> {
  await saveSessionAction(session);
  notify();
}

export async function deleteSession(id: string): Promise<void> {
  await deleteSessionAction(id);
  notify();
}

export async function clearSessions(): Promise<void> {
  await clearSessionsAction();
  notify();
}
