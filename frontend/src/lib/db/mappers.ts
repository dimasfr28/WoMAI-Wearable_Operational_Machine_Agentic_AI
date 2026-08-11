import "server-only";
import type { ChatSessionRow, MachineRow, SopRow } from "@/lib/db/schema";
import type { ChatSession, Machine, Sop } from "@/lib/types";

export function rowToSop(row: SopRow): Sop {
  return {
    id: row.id,
    mode: row.mode,
    title: row.title,
    symptoms: row.symptoms,
    body: row.body,
    steps: row.steps,
    reference: row.reference,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

export function rowToMachine(row: MachineRow): Machine {
  return {
    id: row.id,
    name: row.name,
    type: row.type,
    line: row.line ?? undefined,
    notes: row.notes ?? undefined,
    createdAt: row.createdAt.toISOString(),
  };
}

export function rowToSession(row: ChatSessionRow): ChatSession {
  return {
    id: row.id,
    title: row.title,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
    messages: row.messages,
    lastPrediction: row.lastPrediction ?? undefined,
    machineId: row.machineId ?? undefined,
    machineName: row.machineName ?? undefined,
    checkedSteps: row.checkedSteps,
  };
}
