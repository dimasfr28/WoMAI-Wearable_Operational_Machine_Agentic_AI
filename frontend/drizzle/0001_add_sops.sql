CREATE TYPE "public"."sop_mode" AS ENUM('TWF', 'HDF', 'PWF', 'OSF', 'RNF');--> statement-breakpoint
CREATE TABLE "sops" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"mode" "sop_mode" NOT NULL,
	"title" text NOT NULL,
	"symptoms" text DEFAULT '' NOT NULL,
	"body" text DEFAULT '' NOT NULL,
	"steps" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"reference" text DEFAULT '' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
