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
  machineType?: string; // free-text label, e.g. "Haas" — comfest-18 has no L/M/H concept
  status: string; // e.g. "running" — comfest-18's real Machine.status column
  documentCount: number;
  runCount: number;
  createdAt: string; // ISO
}

// SOP library mandiri — TIDAK terikat failure-mode taxonomy apa pun (backend
// comfest-18 tidak punya konsep itu; prediksinya biner, dijelaskan SHAP
// per-fitur sensor) dan TIDAK di-scope per mesin (global).
export interface Sop {
  id: string;
  title: string;
  symptoms: string; // kata kunci gejala (dipakai pencarian)
  body: string; // deskripsi + tindakan
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
