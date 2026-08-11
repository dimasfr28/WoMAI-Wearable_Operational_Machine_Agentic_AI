import {
  deleteMachineAction,
  getMachineAction,
  loadMachinesAction,
  saveMachineAction,
} from "@/app/actions/machines";
import type { Machine } from "@/lib/types";

// Dipertahankan agar komponen bisa memicu re-fetch setelah mutasi.
export const MACHINES_CHANGED_EVENT = "womai:machines-changed";

function notify(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(MACHINES_CHANGED_EVENT));
  }
}

export async function loadMachines(): Promise<Machine[]> {
  return loadMachinesAction();
}

export async function getMachine(id: string): Promise<Machine | null> {
  return getMachineAction(id);
}

export async function saveMachine(machine: {
  id?: string;
  name: string;
  type: Machine["type"];
  line?: string;
  notes?: string;
}): Promise<Machine> {
  const saved = await saveMachineAction(machine);
  notify();
  return saved;
}

export async function deleteMachine(id: string): Promise<void> {
  await deleteMachineAction(id);
  notify();
}
