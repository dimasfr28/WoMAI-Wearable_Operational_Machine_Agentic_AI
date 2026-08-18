"use server";

import { backendFetch } from "@/lib/backend-fetch";
import type { Sop, SopStep } from "@/lib/types";

interface SopStepApiOut {
  id: string;
  text: string;
  priority: "segera" | "terjadwal";
  estimated_minutes: number;
}

interface SopApiOut {
  id: string;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStepApiOut[];
  reference: string;
  created_at: string;
  updated_at: string;
}

function fromApi(s: SopApiOut): Sop {
  return {
    id: s.id,
    title: s.title,
    symptoms: s.symptoms,
    body: s.body,
    steps: s.steps.map(
      (step): SopStep => ({
        id: step.id,
        text: step.text,
        priority: step.priority,
        estimatedMinutes: step.estimated_minutes,
      }),
    ),
    reference: s.reference,
    createdAt: s.created_at,
    updatedAt: s.updated_at,
  };
}

function toApiSteps(steps: SopStep[]) {
  return steps.map((s) => ({
    id: s.id,
    text: s.text,
    priority: s.priority,
    estimated_minutes: s.estimatedMinutes,
  }));
}

export async function loadSopsAction(): Promise<Sop[]> {
  const resp = await backendFetch("/sops", { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`Failed to load SOP list (${resp.status})`);
  }
  const data = (await resp.json()) as SopApiOut[];
  return data.map(fromApi);
}

export async function saveSopAction(input: {
  id?: string;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStep[];
  reference: string;
}): Promise<Sop> {
  const payload = JSON.stringify({
    title: input.title,
    symptoms: input.symptoms,
    body: input.body,
    steps: toApiSteps(input.steps),
    reference: input.reference,
  });
  const resp = await backendFetch(input.id ? `/sops/${input.id}` : "/sops", {
    method: input.id ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
  });
  if (!resp.ok) {
    throw new Error(`Failed to save SOP (${resp.status})`);
  }
  const data = (await resp.json()) as SopApiOut;
  return fromApi(data);
}

export async function deleteSopAction(id: string): Promise<void> {
  const resp = await backendFetch(`/sops/${id}`, { method: "DELETE" });
  if (!resp.ok) {
    throw new Error(`Failed to delete SOP (${resp.status})`);
  }
}
