"use server";

import { backendFetch } from "@/lib/backend-fetch";
import type { MachineStatus } from "@/lib/types";

interface EarlyWarningApiOut {
  title: string;
  parameter: string;
  parameter_label: string;
  unit: string;
  current_value: number;
  suggested_adjustment: number | null;
  shap_contribution_pct: number;
  recommended_action: string;
  is_anomaly: boolean;
}

interface MachineStatusApiOut {
  operational_status: string;
  last_reading_at: string | null;
  prediction_stability_pct: number | null;
  early_warning: { items: EarlyWarningApiOut[] };
}

function fromApi(s: MachineStatusApiOut): MachineStatus {
  return {
    operationalStatus: s.operational_status,
    lastReadingAt: s.last_reading_at,
    predictionStabilityPct: s.prediction_stability_pct,
    earlyWarning: s.early_warning.items.map((item) => ({
      title: item.title,
      parameter: item.parameter,
      parameterLabel: item.parameter_label,
      unit: item.unit,
      currentValue: item.current_value,
      suggestedAdjustment: item.suggested_adjustment,
      shapContributionPct: item.shap_contribution_pct,
      recommendedAction: item.recommended_action,
      isAnomaly: item.is_anomaly,
    })),
  };
}

export async function getMachineStatusAction(
  machineId: string,
): Promise<MachineStatus | null> {
  const resp = await backendFetch(
    `/machines/${encodeURIComponent(machineId)}/status`,
    { cache: "no-store" },
  );
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new Error(`Gagal memuat status mesin (${resp.status})`);
  }
  const data = (await resp.json()) as MachineStatusApiOut;
  return fromApi(data);
}
