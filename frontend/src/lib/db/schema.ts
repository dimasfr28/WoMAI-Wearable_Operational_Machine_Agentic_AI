import {
  jsonb,
  pgEnum,
  pgSchema,
  pgTable,
  text,
  timestamp,
  uuid,
} from "drizzle-orm/pg-core";
import type {
  PredictionResult,
  WomaiMessage,
  SopStep,
} from "@/lib/types";

// Skema `auth` dikelola Supabase. Kita cukup mereferensikan auth.users(id)
// untuk foreign key; jangan pernah membuat migrasi yang mengubah tabel ini.
const authSchema = pgSchema("auth");
export const authUsers = authSchema.table("users", {
  id: uuid("id").primaryKey(),
});

export const machineType = pgEnum("machine_type", ["L", "M", "H"]);

export const machines = pgTable("machines", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: uuid("user_id")
    .notNull()
    .references(() => authUsers.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  type: machineType("type").notNull(),
  line: text("line"),
  notes: text("notes"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const chatSessions = pgTable("chat_sessions", {
  // id sesi berasal dari frontend (crypto.randomUUID), bukan default DB
  id: uuid("id").primaryKey(),
  userId: uuid("user_id")
    .notNull()
    .references(() => authUsers.id, { onDelete: "cascade" }),
  title: text("title").notNull(),
  machineId: uuid("machine_id").references(() => machines.id, {
    onDelete: "set null",
  }),
  machineName: text("machine_name"),
  lastPrediction: jsonb("last_prediction").$type<PredictionResult>(),
  messages: jsonb("messages").$type<WomaiMessage[]>().notNull(),
  checkedSteps: jsonb("checked_steps")
    .$type<Record<string, boolean>>()
    .notNull()
    .default({}),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

// ── SOP knowledge base (global; bukan per-user) ──────────────
// Failure mode AI4I 2020 yang dicakup SOP. Dipakai pipeline retrieval backend.
export const sopMode = pgEnum("sop_mode", ["TWF", "HDF", "PWF", "OSF", "RNF"]);

export const sops = pgTable("sops", {
  id: uuid("id").primaryKey().defaultRandom(),
  mode: sopMode("mode").notNull(),
  title: text("title").notNull(),
  symptoms: text("symptoms").notNull().default(""),
  body: text("body").notNull().default(""),
  steps: jsonb("steps").$type<SopStep[]>().notNull().default([]),
  reference: text("reference").notNull().default(""),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export type MachineRow = typeof machines.$inferSelect;
export type ChatSessionRow = typeof chatSessions.$inferSelect;
export type SopRow = typeof sops.$inferSelect;
