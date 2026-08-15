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

// "Probability Failure in +10 Minute" (rancangan.txt Section 5) — model
// TERPISAH dari ReportPrediction (menjawab pertanyaan berbeda: "akan gagal
// dalam N menit ke depan?", bukan "sedang gagal sekarang?"). null kalau model
// horizon gagal saat report digenerate (backend tetap sukses tanpa itu).
export interface ReportHorizonPrediction {
  predictedLabel: boolean;
  failureProbability: number; // 0..1
  modelVersion: string;
  threshold: number; // 0..1
  horizonMinutes: number;
}

export interface ReportData {
  sensor: ReportSensorSnapshot;
  prediction: ReportPrediction;
  horizonPrediction: ReportHorizonPrediction | null;
  shap: ReportShap;
  recommendations: ReportRecommendations;
  rootCause: ReportRootCause | null;
  partPrices: ReportPartPrice[];
  aiExplanation: string | null;
  recommendedAction: ReportRecommendedAction | null;
  // Machine Diagnosis "AI Explanation" panel (rancangan.txt Section 5):
  // causeAnalysisShort — ringkasan root cause maks 1 kalimat/40 kata, 1 part.
  // null kalau predictedLabel=false (CRAG tidak dijalankan untuk kondisi normal).
  causeAnalysisShort: string | null;
  // suggestionGeneral — saran perbaikan istilah general/non-numerik (bukan
  // angka sensor mentah), arah over/under dari worst-case delta (KNN).
  suggestionGeneral: string | null;
  finalReportText: string;
  llmModel: string;
  createdAt: string; // ISO
}

// AI Early Warning panel (rancangan.txt Section 5) — satu kartu per parameter
// sensor, urutan dari SHAP contribution paling besar.
export interface EarlyWarningItem {
  title: string;
  parameter: string;
  parameterLabel: string;
  unit: string;
  currentValue: number;
  suggestedAdjustment: number | null;
  shapContributionPct: number;
  recommendedAction: string;
  // IQR outlier per RUN ID (rancangan.txt) — true = highlight bayangan merah.
  isAnomaly: boolean;
}

export interface MachineStatus {
  operationalStatus: string; // "RUNNING" | "WARNING" | "IDLE" | "OFFLINE"
  lastReadingAt: string | null; // ISO
  predictionStabilityPct: number | null;
  earlyWarning: EarlyWarningItem[];
}

// Machine Report (rancangan.txt Section 7) — satu row per PDF ter-generate.
export interface MachineReportItem {
  id: string;
  reportNumber: string;
  operatingStatus: string; // "Normal" | "Warning" | "Failure"
  createdAt: string; // ISO
}

// Dokumen manual servis (PDF) yang sudah di-ingest ke knowledge base RAG —
// read-only di frontend (upload/hapus tetap lewat backend Swagger/script
// migrasi untuk saat ini, lihat KnowledgeBaseDocuments di /sop).
export interface KnowledgeBaseDocument {
  id: string;
  originalFilename: string | null;
  docName: string;
  status: string; // "processing" | "completed" | "rejected_duplicate" | "failed"
  chunkCount: number;
  uploadedAt: string; // ISO
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
