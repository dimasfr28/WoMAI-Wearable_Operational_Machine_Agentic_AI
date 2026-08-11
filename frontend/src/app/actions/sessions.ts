"use server";

import { and, desc, eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { rowToSession } from "@/lib/db/mappers";
import { chatSessions } from "@/lib/db/schema";
import { requireUser } from "@/lib/supabase/server";
import type { ChatSession } from "@/lib/types";

export async function loadSessionsAction(): Promise<ChatSession[]> {
  const user = await requireUser();
  const rows = await db
    .select()
    .from(chatSessions)
    .where(eq(chatSessions.userId, user.id))
    .orderBy(desc(chatSessions.updatedAt));
  return rows.map(rowToSession);
}

export async function getSessionAction(
  id: string,
): Promise<ChatSession | null> {
  const user = await requireUser();
  const rows = await db
    .select()
    .from(chatSessions)
    .where(and(eq(chatSessions.id, id), eq(chatSessions.userId, user.id)))
    .limit(1);
  return rows[0] ? rowToSession(rows[0]) : null;
}

/** Upsert sesi milik user. Konflik pada primary key -> update. */
export async function saveSessionAction(session: ChatSession): Promise<void> {
  const user = await requireUser();
  const values = {
    id: session.id,
    userId: user.id,
    title: session.title,
    machineId: session.machineId ?? null,
    machineName: session.machineName ?? null,
    lastPrediction: session.lastPrediction ?? null,
    messages: session.messages,
    checkedSteps: session.checkedSteps,
    createdAt: new Date(session.createdAt),
    updatedAt: new Date(session.updatedAt),
  };

  await db
    .insert(chatSessions)
    .values(values)
    .onConflictDoUpdate({
      target: chatSessions.id,
      // Batasi update ke pemilik agar id sesi user lain tak bisa ditimpa.
      setWhere: eq(chatSessions.userId, user.id),
      set: {
        title: values.title,
        machineId: values.machineId,
        machineName: values.machineName,
        lastPrediction: values.lastPrediction,
        messages: values.messages,
        checkedSteps: values.checkedSteps,
        updatedAt: values.updatedAt,
      },
    });
}

export async function deleteSessionAction(id: string): Promise<void> {
  const user = await requireUser();
  await db
    .delete(chatSessions)
    .where(and(eq(chatSessions.id, id), eq(chatSessions.userId, user.id)));
}

export async function clearSessionsAction(): Promise<void> {
  const user = await requireUser();
  await db.delete(chatSessions).where(eq(chatSessions.userId, user.id));
}
