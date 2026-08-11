import { defineConfig } from "drizzle-kit";

// DATABASE_URL diambil dari environment. Untuk menjalankan drizzle-kit di luar
// container, muat dari .env terlebih dahulu (mis. `dotenv -e ../.env -- ...`).
const url = process.env.DATABASE_URL;
if (!url) {
  throw new Error("DATABASE_URL wajib di-set untuk drizzle-kit.");
}

export default defineConfig({
  schema: "./src/lib/db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: { url },
  // Jangan pernah menghasilkan migrasi untuk skema `auth` milik Supabase.
  schemaFilter: ["public"],
  casing: "snake_case",
});
