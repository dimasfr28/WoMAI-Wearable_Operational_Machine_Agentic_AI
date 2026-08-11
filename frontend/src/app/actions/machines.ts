"use server";

import { randomUUID } from "node:crypto";
import { requireSession } from "@/lib/auth/session";
import type { Machine } from "@/lib/types";

// Data contoh in-memory untuk fondasi migrasi frontend WO.M.AI — TIDAK
// persisten (reset saat server Next.js restart). Diganti pemanggilan REST
// API comfest-18 (mis. GET/POST/PATCH/DELETE /machines) di sub-project
// berikutnya (lihat docs/superpowers/specs/2026-08-11-womai-frontend-foundation-design.md).
let machinesStore: Machine[] = [
  {
    id: "m-demo-1",
    name: "CNC Mill 01",
    type: "M",
    line: "Line A",
    createdAt: new Date().toISOString(),
  },
  {
    id: "m-demo-2",
    name: "CNC Lathe 02",
    type: "H",
    line: "Line B",
    notes: "Overhaul terakhir bulan lalu",
    createdAt: new Date().toISOString(),
  },
];

export async function loadMachinesAction(): Promise<Machine[]> {
  await requireSession();
  return machinesStore;
}

export async function getMachineAction(id: string): Promise<Machine | null> {
  await requireSession();
  return machinesStore.find((m) => m.id === id) ?? null;
}

export async function saveMachineAction(input: {
  id?: string;
  name: string;
  type: Machine["type"];
  line?: string;
  notes?: string;
}): Promise<Machine> {
  await requireSession();

  if (input.id) {
    const idx = machinesStore.findIndex((m) => m.id === input.id);
    if (idx >= 0) {
      const updated: Machine = {
        ...machinesStore[idx],
        ...input,
        id: input.id,
      };
      machinesStore = [
        ...machinesStore.slice(0, idx),
        updated,
        ...machinesStore.slice(idx + 1),
      ];
      return updated;
    }
  }

  const machine: Machine = {
    id: input.id ?? randomUUID(),
    name: input.name,
    type: input.type,
    line: input.line,
    notes: input.notes,
    createdAt: new Date().toISOString(),
  };
  machinesStore = [...machinesStore, machine];
  return machine;
}

export async function deleteMachineAction(id: string): Promise<void> {
  await requireSession();
  machinesStore = machinesStore.filter((m) => m.id !== id);
}
