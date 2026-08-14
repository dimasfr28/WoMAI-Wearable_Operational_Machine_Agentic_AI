import type { UIMessage } from "ai";

export type RiskLevel = "rendah" | "sedang" | "tinggi";

export interface PredictionResult {
  label: boolean; // true = model memprediksi kegagalan
  probability: number; // 0..1, failure_probability dari backend
  healthScore: number; // 0..100, (1-probability)*100
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

export interface ReportSensorSnapshot {
  id: string;
  readingTimestamp: string; // ISO
  airTemperatureK: number;
  processTemperatureK: number;
  rotationalSpeedRpm: number;
  toolWearMin: number;
}

export interface ReportPrediction {
  id: string;
  predictedLabel: boolean;
  failureProbability: number; // 0..1
  healthScore: number; // 0..100
  modelVersion: string;
  threshold: number; // 0..1
}

export interface ReportShapFeature {
  featureName: string;
  value: number;
  shapValue: number;
  rank: number;
}

export interface ReportShap {
  baseValue: number;
  features: ReportShapFeature[];
}

export interface ReportNeighborRow {
  airTemperatureK: number;
  processTemperatureK: number;
  rotationalSpeedRpm: number;
  toolWearMin: number;
  machineFailure: boolean;
}

export interface ReportNeighborGroup {
  distances: number[];
  rows: ReportNeighborRow[];
}

export interface ReportRecommendations {
  nearestFailure: ReportNeighborGroup;
  nearestNoFailure: ReportNeighborGroup;
  worstCaseDelta: {
    // Kunci di sini adalah NAMA TAMPILAN dari backend (mis. "Rotational speed
    // rpm"), bukan raw snake_case -- lihat RAW_TO_MODEL_COL di
    // backend/app/ml/predictor.py. Jangan coba petakan ulang ke camelCase.
    nearestSafePoint: Record<string, number | boolean> | null;
    suggestedAdjustments: Record<string, number>;
  };
}

export interface ReportRetrievedChunk {
  chunkId: string;
  docName?: string;
  heading1?: string;
  heading2?: string;
  content: string;
}

export interface ReportRootCause {
  query: string;
  answer: string;
  usedWebFallback: boolean;
  retrievedChunkIds: string[];
  retrievedChunks: ReportRetrievedChunk[];
}

export interface ReportPartPrice {
  partName: string;
  priceMin: number | null;
  priceMax: number | null;
  currency: string;
  sourceUrl: string | null;
}

// feature/currentValue/targetValue dihitung deterministik backend dari
// worst_case_delta -- hanya why/expectedImpact yang teks bebas dari LLM.
export interface ReportRecommendedAction {
  feature: string;
  currentValue: number;
  targetValue: number;
  why: string;
  expectedImpact: string;
}

export interface ReportData {
  sensor: ReportSensorSnapshot;
  prediction: ReportPrediction;
  shap: ReportShap;
  recommendations: ReportRecommendations;
  rootCause: ReportRootCause | null;
  partPrices: ReportPartPrice[];
  aiExplanation: string | null;
  recommendedAction: ReportRecommendedAction | null;
  finalReportText: string;
  llmModel: string;
  createdAt: string; // ISO
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
