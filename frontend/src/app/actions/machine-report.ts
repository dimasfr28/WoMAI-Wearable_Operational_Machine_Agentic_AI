"use server";

import { backendFetch } from "@/lib/backend-fetch";
import type { MachineReportItem } from "@/lib/types";

interface MachineReportApiOut {
  id: string;
  report_number: string;
  operating_status: string;
  created_at: string;
}

function fromApi(r: MachineReportApiOut): MachineReportItem {
  return {
    id: r.id,
    reportNumber: r.report_number,
    operatingStatus: r.operating_status,
    createdAt: r.created_at,
  };
}

export async function getLatestMachineReportAction(
  machineId: string,
): Promise<MachineReportItem | null> {
  const resp = await backendFetch(
    `/machine-report/latest?machine_id=${encodeURIComponent(machineId)}`,
    { cache: "no-store" },
  );
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new Error(`Gagal memuat Machine Report (${resp.status})`);
  }
  const data = (await resp.json()) as MachineReportApiOut;
  return fromApi(data);
}

export async function listMachineReportsAction(
  machineId: string,
): Promise<MachineReportItem[]> {
  const resp = await backendFetch(
    `/machine-report/history?machine_id=${encodeURIComponent(machineId)}`,
    { cache: "no-store" },
  );
  if (!resp.ok) {
    throw new Error(`Gagal memuat riwayat Machine Report (${resp.status})`);
  }
  const data = (await resp.json()) as MachineReportApiOut[];
  return data.map(fromApi);
}
