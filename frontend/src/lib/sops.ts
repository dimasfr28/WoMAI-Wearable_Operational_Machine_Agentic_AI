import {
  deleteSopAction,
  loadSopsAction,
  saveSopAction,
} from "@/app/actions/sop";
import type { Sop, SopStep } from "@/lib/types";

// Dipertahankan agar komponen bisa memicu re-fetch setelah mutasi.
export const SOPS_CHANGED_EVENT = "womai:sops-changed";

function notify(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SOPS_CHANGED_EVENT));
  }
}

export async function loadSops(): Promise<Sop[]> {
  return loadSopsAction();
}

export async function saveSop(sop: {
  id?: string;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStep[];
  reference: string;
}): Promise<Sop> {
  const saved = await saveSopAction(sop);
  notify();
  return saved;
}

export async function deleteSop(id: string): Promise<void> {
  await deleteSopAction(id);
  notify();
}
