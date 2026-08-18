"use server";

import { backendFetch } from "@/lib/backend-fetch";
import type { Machine } from "@/lib/types";

interface MachineApiOut {
  id: string;
  name: string;
  machine_type: string | null;
  status: string;
  created_at: string;
  document_count: number;
  run_count: number;
}

function fromApi(m: MachineApiOut): Machine {
  return {
    id: m.id,
    name: m.name,
    machineType: m.machine_type ?? undefined,
    status: m.status,
    documentCount: m.document_count,
    runCount: m.run_count,
    createdAt: m.created_at,
  };
}

export async function loadMachinesAction(): Promise<Machine[]> {
  const resp = await backendFetch("/machines", { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`Failed to load machine list (${resp.status})`);
  }
  const data = (await resp.json()) as MachineApiOut[];
  return data.map(fromApi);
}

export async function getMachineAction(id: string): Promise<Machine | null> {
  const resp = await backendFetch(`/machines/${id}`, { cache: "no-store" });
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new Error(`Failed to load machine (${resp.status})`);
  }
  const data = (await resp.json()) as MachineApiOut;
  return fromApi(data);
}

export async function saveMachineAction(input: {
  id?: string;
  name: string;
  machineType?: string;
}): Promise<Machine> {
  const body = JSON.stringify({
    name: input.name,
    machine_type: input.machineType || null,
  });
  const resp = await backendFetch(
    input.id ? `/machines/${input.id}` : "/machines",
    {
      method: input.id ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body,
    },
  );
  if (!resp.ok) {
    throw new Error(`Failed to save machine (${resp.status})`);
  }
  const data = (await resp.json()) as MachineApiOut;
  return fromApi(data);
}

export async function deleteMachineAction(id: string): Promise<void> {
  const resp = await backendFetch(`/machines/${id}`, { method: "DELETE" });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? `Failed to delete machine (${resp.status})`);
  }
}
