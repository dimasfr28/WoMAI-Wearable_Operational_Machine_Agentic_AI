"use server";

import { asc, eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { rowToSop } from "@/lib/db/mappers";
import { sops } from "@/lib/db/schema";
import { requireUser } from "@/lib/supabase/server";
import type { Sop, SopMode, SopStep } from "@/lib/types";

// URL backend (server-side). Di Docker: http://backend:8000; lokal: localhost.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

/**
 * Minta backend memuat ulang knowledge base SOP dari DB & re-embed ke Redis.
 * Best-effort: backend mungkin tidak berjalan (profile terpisah) — jangan
 * gagalkan mutasi hanya karena reseed tak terjangkau.
 */
async function triggerReseed(): Promise<void> {
  try {
    await fetch(`${BACKEND_URL}/sop/reseed`, {
      method: "POST",
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    // abaikan — index akan tersinkron saat backend berikutnya restart/seed.
  }
}

export async function loadSopsAction(): Promise<Sop[]> {
  await requireUser();
  const rows = await db.select().from(sops).orderBy(asc(sops.mode), asc(sops.createdAt));
  return rows.map(rowToSop);
}

/** Upsert dokumen SOP. `id` opsional (baru → di-generate DB). Global (tidak per-user). */
export async function saveSopAction(input: {
  id?: string;
  mode: SopMode;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStep[];
  reference: string;
}): Promise<Sop> {
  await requireUser();
  const values = {
    mode: input.mode,
    title: input.title,
    symptoms: input.symptoms,
    body: input.body,
    steps: input.steps,
    reference: input.reference,
    updatedAt: new Date(),
  };

  let saved: Sop;
  if (input.id) {
    const updated = await db
      .update(sops)
      .set(values)
      .where(eq(sops.id, input.id))
      .returning();
    saved = updated[0]
      ? rowToSop(updated[0])
      : rowToSop(
          (await db.insert(sops).values({ ...values, id: input.id }).returning())[0],
        );
  } else {
    const inserted = await db.insert(sops).values(values).returning();
    saved = rowToSop(inserted[0]);
  }

  await triggerReseed();
  return saved;
}

export async function deleteSopAction(id: string): Promise<void> {
  await requireUser();
  await db.delete(sops).where(eq(sops.id, id));
  await triggerReseed();
}
