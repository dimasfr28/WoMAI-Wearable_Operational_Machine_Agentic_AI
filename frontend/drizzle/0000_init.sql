CREATE TYPE "public"."machine_type" AS ENUM('L', 'M', 'H');--> statement-breakpoint
-- Catatan: "auth"."users" dikelola Supabase dan sudah ada; JANGAN dibuat ulang.
-- (Statement CREATE TABLE auth.users dari drizzle-kit sengaja dihapus.)
CREATE TABLE "chat_sessions" (
	"id" uuid PRIMARY KEY NOT NULL,
	"user_id" uuid NOT NULL,
	"title" text NOT NULL,
	"machine_id" uuid,
	"machine_name" text,
	"last_prediction" jsonb,
	"messages" jsonb NOT NULL,
	"checked_steps" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "machines" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" uuid NOT NULL,
	"name" text NOT NULL,
	"type" "machine_type" NOT NULL,
	"line" text,
	"notes" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "chat_sessions" ADD CONSTRAINT "chat_sessions_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "chat_sessions" ADD CONSTRAINT "chat_sessions_machine_id_machines_id_fk" FOREIGN KEY ("machine_id") REFERENCES "public"."machines"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "machines" ADD CONSTRAINT "machines_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
-- ============================================================
-- Row Level Security (jaring pengaman untuk jalur anon/PostgREST).
-- Query aplikasi lewat Drizzle (koneksi owner) tetap di-scope user_id
-- di kode; RLS memastikan akses role `authenticated` hanya baris miliknya.
-- ============================================================
ALTER TABLE "machines" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "chat_sessions" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE POLICY "machines_owner" ON "machines"
	FOR ALL TO authenticated
	USING ("user_id" = (select auth.uid()))
	WITH CHECK ("user_id" = (select auth.uid()));--> statement-breakpoint
CREATE POLICY "chat_sessions_owner" ON "chat_sessions"
	FOR ALL TO authenticated
	USING ("user_id" = (select auth.uid()))
	WITH CHECK ("user_id" = (select auth.uid()));