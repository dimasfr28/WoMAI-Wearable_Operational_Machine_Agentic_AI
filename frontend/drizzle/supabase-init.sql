-- ============================================================
-- WO.M.AI — skema database untuk Supabase
-- Jalankan sekali di Supabase Dashboard → SQL Editor → New query → Run.
-- Idempotent: aman dijalankan ulang (pakai IF NOT EXISTS / DROP POLICY IF EXISTS).
--
-- CATATAN: skema `auth` (auth.users, auth.uid) dikelola Supabase dan sudah ada.
-- File ini HANYA membuat objek di skema `public` dan mereferensikan auth.users
-- lewat foreign key. Jangan membuat/mengubah tabel di skema auth.
-- ============================================================

-- ---------- Enum tipe mesin (L/M/H) ----------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'machine_type') THEN
    CREATE TYPE "public"."machine_type" AS ENUM ('L', 'M', 'H');
  END IF;
END
$$;

-- ---------- Tabel: machines ----------
CREATE TABLE IF NOT EXISTS "public"."machines" (
  "id"         uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "user_id"    uuid NOT NULL REFERENCES "auth"."users"("id") ON DELETE CASCADE,
  "name"       text NOT NULL,
  "type"       "public"."machine_type" NOT NULL,
  "line"       text,
  "notes"      text,
  "created_at" timestamptz DEFAULT now() NOT NULL
);

-- ---------- Tabel: chat_sessions ----------
-- id sesi berasal dari frontend (crypto.randomUUID), jadi TANPA default DB.
CREATE TABLE IF NOT EXISTS "public"."chat_sessions" (
  "id"              uuid PRIMARY KEY NOT NULL,
  "user_id"         uuid NOT NULL REFERENCES "auth"."users"("id") ON DELETE CASCADE,
  "title"           text NOT NULL,
  "machine_id"      uuid REFERENCES "public"."machines"("id") ON DELETE SET NULL,
  "machine_name"    text,
  "last_prediction" jsonb,
  "messages"        jsonb NOT NULL,
  "checked_steps"   jsonb DEFAULT '{}'::jsonb NOT NULL,
  "created_at"      timestamptz DEFAULT now() NOT NULL,
  "updated_at"      timestamptz DEFAULT now() NOT NULL
);

-- ---------- Enum failure mode SOP (TWF/HDF/PWF/OSF/RNF) ----------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sop_mode') THEN
    CREATE TYPE "public"."sop_mode" AS ENUM ('TWF', 'HDF', 'PWF', 'OSF', 'RNF');
  END IF;
END
$$;

-- ---------- Tabel: sops (knowledge base GLOBAL, bukan per-user) ----------
-- Dibaca pipeline retrieval backend (di-embed ke Redis vector index).
CREATE TABLE IF NOT EXISTS "public"."sops" (
  "id"         uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "mode"       "public"."sop_mode" NOT NULL,
  "title"      text NOT NULL,
  "symptoms"   text DEFAULT '' NOT NULL,
  "body"       text DEFAULT '' NOT NULL,
  "steps"      jsonb DEFAULT '[]'::jsonb NOT NULL,
  "reference"  text DEFAULT '' NOT NULL,
  "created_at" timestamptz DEFAULT now() NOT NULL,
  "updated_at" timestamptz DEFAULT now() NOT NULL
);

-- Indeks bantu untuk query per-user (opsional tapi berguna).
CREATE INDEX IF NOT EXISTS "machines_user_id_idx"      ON "public"."machines" ("user_id");
CREATE INDEX IF NOT EXISTS "chat_sessions_user_id_idx" ON "public"."chat_sessions" ("user_id");
CREATE INDEX IF NOT EXISTS "sops_mode_idx"             ON "public"."sops" ("mode");

-- ============================================================
-- Row Level Security — jaring pengaman untuk role `authenticated`
-- (jalur anon/PostgREST). Query aplikasi lewat Drizzle (koneksi owner)
-- sudah di-scope user_id di kode; RLS memastikan role authenticated
-- hanya bisa mengakses baris miliknya sendiri.
-- ============================================================
ALTER TABLE "public"."machines"      ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."chat_sessions" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."sops"          ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "machines_owner" ON "public"."machines";
CREATE POLICY "machines_owner" ON "public"."machines"
  FOR ALL TO authenticated
  USING ("user_id" = (SELECT auth.uid()))
  WITH CHECK ("user_id" = (SELECT auth.uid()));

DROP POLICY IF EXISTS "chat_sessions_owner" ON "public"."chat_sessions";
CREATE POLICY "chat_sessions_owner" ON "public"."chat_sessions"
  FOR ALL TO authenticated
  USING ("user_id" = (SELECT auth.uid()))
  WITH CHECK ("user_id" = (SELECT auth.uid()));

-- SOP = knowledge base bersama: setiap user login boleh baca & kelola.
DROP POLICY IF EXISTS "sops_authenticated" ON "public"."sops";
CREATE POLICY "sops_authenticated" ON "public"."sops"
  FOR ALL TO authenticated
  USING (true)
  WITH CHECK (true);
