"use server";

import { backendFetch } from "@/lib/backend-fetch";

export async function restartSimulationAction(machineId: string): Promise<void> {
  const resp = await backendFetch(
    `/sensor/machine-diagnosis?machine_id=${encodeURIComponent(machineId)}`,
    { method: "POST", cache: "no-store" },
  );
  if (!resp.ok) {
    throw new Error(`Failed to restart simulation (${resp.status})`);
  }
}
