import "server-only";
import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "@/lib/db/schema";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
  throw new Error(
    "DATABASE_URL belum di-set. Isi dengan connection string pooler Supabase.",
  );
}

// Reuse koneksi antar hot-reload dev agar tidak membocorkan pool.
const globalForDb = globalThis as unknown as {
  __womaiPg?: ReturnType<typeof postgres>;
};

// Pooler Supabase (mode transaction) tidak mendukung prepared statements.
const client =
  globalForDb.__womaiPg ??
  postgres(connectionString, { prepare: false });

if (process.env.NODE_ENV !== "production") {
  globalForDb.__womaiPg = client;
}

export const db = drizzle(client, { schema });
