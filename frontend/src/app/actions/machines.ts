"use server";

import { and, asc, eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { rowToMachine } from "@/lib/db/mappers";
import { machines } from "@/lib/db/schema";
import { requireUser } from "@/lib/supabase/server";
import type { Machine } from "@/lib/types";

export async function loadMachinesAction(): Promise<Machine[]> {
  const user = await requireUser();
  const rows = await db
    .select()
    .from(machines)
    .where(eq(machines.userId, user.id))
    .orderBy(asc(machines.createdAt));
  return rows.map(rowToMachine);
}

export async function getMachineAction(id: string): Promise<Machine | null> {
  const user = await requireUser();
  const rows = await db
    .select()
    .from(machines)
    .where(and(eq(machines.id, id), eq(machines.userId, user.id)))
    .limit(1);
  return rows[0] ? rowToMachine(rows[0]) : null;
}

/** Upsert mesin milik user. `id` opsional (baru -> di-generate DB). */
export async function saveMachineAction(input: {
  id?: string;
  name: string;
  type: Machine["type"];
  line?: string;
  notes?: string;
}): Promise<Machine> {
  const user = await requireUser();
  const values = {
    name: input.name,
    type: input.type,
    line: input.line ?? null,
    notes: input.notes ?? null,
    userId: user.id,
  };

  if (input.id) {
    // Update hanya bila baris milik user (scope ganda: where + RLS).
    const updated = await db
      .update(machines)
      .set(values)
      .where(and(eq(machines.id, input.id), eq(machines.userId, user.id)))
      .returning();
    if (updated[0]) return rowToMachine(updated[0]);
    // Tidak ada baris (mis. id dari device lama) -> insert dengan id tsb.
    const inserted = await db
      .insert(machines)
      .values({ ...values, id: input.id })
      .returning();
    return rowToMachine(inserted[0]);
  }

  const inserted = await db.insert(machines).values(values).returning();
  return rowToMachine(inserted[0]);
}

export async function deleteMachineAction(id: string): Promise<void> {
  const user = await requireUser();
  await db
    .delete(machines)
    .where(and(eq(machines.id, id), eq(machines.userId, user.id)));
}
