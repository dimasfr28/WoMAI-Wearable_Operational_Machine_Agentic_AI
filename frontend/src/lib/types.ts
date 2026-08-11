import type { UIMessage } from "ai";

export type FailureType = "TWF" | "HDF" | "PWF" | "OSF" | "RNF" | "NONE";
export type RiskLevel = "rendah" | "sedang" | "tinggi";

export interface PredictionResult {
  failureProbability: number; // 0..1
  failureType: FailureType;
  failureTypeLabel: string;
  riskLevel: RiskLevel;
}

export interface ShapContribution {
  feature: string;
  value: number; // kontribusi SHAP bertanda (+ menaikkan risiko)
}

export interface ShapResult {
  contributions: ShapContribution[];
}

export interface SopStep {
  id: string;
  text: string;
  priority: "segera" | "terjadwal";
  estimatedMinutes: number;
}

export interface SopPlan {
  title: string;
  steps: SopStep[];
}

export interface DowntimeEstimate {
  costPerHourIdr: number;
  estimatedRepairHours: number;
  projections: { delayHours: number; additionalLossIdr: number }[];
}

export interface AgentStatus {
  message: string;
}

export type WomaiDataParts = {
  status: AgentStatus;
  prediction: PredictionResult;
  shap: ShapResult;
  sop: SopPlan;
  downtime: DowntimeEstimate;
};

export type WomaiMessage = UIMessage<unknown, WomaiDataParts>;

export interface Machine {
  id: string;
  name: string;
  type: "L" | "M" | "H";
  line?: string;
  notes?: string;
  createdAt: string; // ISO
}

// Failure mode yang dicakup knowledge base SOP (selaras AI4I 2020 & backend).
export type SopMode = "TWF" | "HDF" | "PWF" | "OSF" | "RNF";

export const SOP_MODE_LABEL: Record<SopMode, string> = {
  TWF: "Tool Wear Failure",
  HDF: "Heat Dissipation Failure",
  PWF: "Power Failure",
  OSF: "Overstrain Failure",
  RNF: "Random Failure",
};

// Dokumen SOP terkurasi — knowledge base global yang dipakai pipeline retrieval.
export interface Sop {
  id: string;
  mode: SopMode;
  title: string;
  symptoms: string; // kata kunci gejala (dipakai embedding retrieval)
  body: string; // deskripsi + tindakan (teks yang di-embed)
  steps: SopStep[];
  reference: string;
  createdAt: string; // ISO
  updatedAt: string; // ISO
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string; // ISO
  updatedAt: string; // ISO
  messages: WomaiMessage[];
  lastPrediction?: PredictionResult;
  machineId?: string;
  machineName?: string;
  checkedSteps: Record<string, boolean>; // SopStep.id -> dicentang
}
