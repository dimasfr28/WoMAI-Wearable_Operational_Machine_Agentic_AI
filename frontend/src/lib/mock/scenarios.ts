import type {
  DowntimeEstimate,
  PredictionResult,
  ShapResult,
  SopPlan,
} from "@/lib/types";

export type ScenarioKey = "hdf" | "osf" | "twf" | "pwf" | "none";

export interface MockScenario {
  key: ScenarioKey;
  responseText: string;
  prediction: PredictionResult;
  shap?: ShapResult;
  sop?: SopPlan;
  downtime?: DowntimeEstimate;
}

export interface ManualParams {
  type: "L" | "M" | "H";
  airTemp: number;
  processTemp: number;
  rpm: number;
  torque: number;
  toolWear: number;
}

export const MANUAL_PREFIX = "Input manual parameter mesin";

export function formatManualMessage(p: ManualParams): string {
  return (
    `${MANUAL_PREFIX} - Tipe: ${p.type}, Suhu udara: ${p.airTemp} K, ` +
    `Suhu proses: ${p.processTemp} K, Kecepatan putar: ${p.rpm} rpm, ` +
    `Torsi: ${p.torque} Nm, Tool wear: ${p.toolWear} min`
  );
}

export function parseManualInput(text: string): ManualParams | null {
  if (!text.startsWith(MANUAL_PREFIX)) return null;
  const type = /Tipe:\s*([LMH])/.exec(text)?.[1];
  const airTemp = /Suhu udara:\s*([\d.]+)/.exec(text)?.[1];
  const processTemp = /Suhu proses:\s*([\d.]+)/.exec(text)?.[1];
  const rpm = /Kecepatan putar:\s*([\d.]+)/.exec(text)?.[1];
  const torque = /Torsi:\s*([\d.]+)/.exec(text)?.[1];
  const toolWear = /Tool wear:\s*([\d.]+)/.exec(text)?.[1];
  if (!type || !airTemp || !processTemp || !rpm || !torque || !toolWear) {
    return null;
  }
  return {
    type: type as ManualParams["type"],
    airTemp: Number(airTemp),
    processTemp: Number(processTemp),
    rpm: Number(rpm),
    torque: Number(torque),
    toolWear: Number(toolWear),
  };
}

const KEYWORDS: [ScenarioKey, string[]][] = [
  ["hdf", ["suhu", "panas", "temperatur", "overheat"]],
  ["osf", ["torsi", "beban", "overstrain"]],
  ["twf", ["aus", "tool wear", "pahat"]],
  ["pwf", ["daya", "listrik", "power"]],
];

export function pickScenario(input: string): MockScenario {
  const manual = parseManualInput(input);
  if (manual) {
    if (manual.processTemp >= 311) return SCENARIOS.hdf;
    if (manual.torque >= 60) return SCENARIOS.osf;
    if (manual.toolWear >= 200) return SCENARIOS.twf;
    if (manual.rpm < 1300) return SCENARIOS.pwf;
    return SCENARIOS.none;
  }
  const lower = input.toLowerCase();
  for (const [key, words] of KEYWORDS) {
    if (words.some((w) => lower.includes(w))) return SCENARIOS[key];
  }
  return SCENARIOS.none;
}

export const SCENARIOS: Record<ScenarioKey, MockScenario> = {
  hdf: {
    key: "hdf",
    responseText:
      "Berdasarkan parameter yang kamu sebutkan, model mendeteksi indikasi Heat Dissipation Failure (HDF) dengan probabilitas 87%. Pendorong utamanya adalah suhu proses yang tinggi dan selisih suhu udara-proses yang menyempit, sehingga pembuangan panas tidak efektif. Saya sudah siapkan rencana tindakan di bawah. Prioritaskan langkah berlabel Segera, dan perhatikan estimasi kerugian bila perbaikan ditunda.",
    prediction: {
      probability: 0.87,
      label: true,
      healthScore: 13,
      riskLevel: "tinggi",
    },
    shap: {
      contributions: [
        { feature: "Suhu proses [K]", value: 0.34 },
        { feature: "Selisih suhu udara-proses", value: 0.21 },
        { feature: "Kecepatan putar [rpm]", value: 0.12 },
        { feature: "Torsi [Nm]", value: 0.05 },
        { feature: "Tipe mesin (M)", value: -0.04 },
      ],
    },
    sop: {
      title: "Penanganan Heat Dissipation Failure",
      steps: [
        {
          id: "hdf-1",
          text: "Turunkan beban mesin ke ≤50% dan pantau tren suhu proses",
          priority: "segera",
          estimatedMinutes: 10,
        },
        {
          id: "hdf-2",
          text: "Periksa dan bersihkan sistem pendingin (kipas, heatsink, saluran udara)",
          priority: "segera",
          estimatedMinutes: 15,
        },
        {
          id: "hdf-3",
          text: "Ukur selisih suhu udara-proses; pastikan kembali di atas 8,6 K",
          priority: "segera",
          estimatedMinutes: 20,
        },
        {
          id: "hdf-4",
          text: "Inspeksi termal menyeluruh pada bearing dan gearbox",
          priority: "terjadwal",
          estimatedMinutes: 45,
        },
        {
          id: "hdf-5",
          text: "Catat kejadian di log maintenance dan jadwalkan pengecekan ulang 24 jam",
          priority: "terjadwal",
          estimatedMinutes: 30,
        },
      ],
    },
    downtime: {
      costPerHourIdr: 12_500_000,
      estimatedRepairHours: 4,
      projections: [
        { delayHours: 24, additionalLossIdr: 300_000_000 },
        { delayHours: 48, additionalLossIdr: 600_000_000 },
      ],
    },
  },
  osf: {
    key: "osf",
    responseText:
      "Parameter menunjukkan indikasi Overstrain Failure (OSF) dengan probabilitas 82%. Kombinasi torsi tinggi dan tool wear yang menumpuk membuat beban melewati ambang aman material. Ikuti rencana tindakan di bawah dan kurangi beban sementara sebelum inspeksi.",
    prediction: {
      probability: 0.82,
      label: true,
      healthScore: 18,
      riskLevel: "tinggi",
    },
    shap: {
      contributions: [
        { feature: "Torsi [Nm]", value: 0.38 },
        { feature: "Tool wear [min]", value: 0.27 },
        { feature: "Tipe mesin (L)", value: 0.09 },
        { feature: "Suhu proses [K]", value: -0.05 },
        { feature: "Kecepatan putar [rpm]", value: -0.08 },
      ],
    },
    sop: {
      title: "Penanganan Overstrain Failure",
      steps: [
        {
          id: "osf-1",
          text: "Kurangi torsi operasi di bawah ambang aman tipe material",
          priority: "segera",
          estimatedMinutes: 5,
        },
        {
          id: "osf-2",
          text: "Inspeksi visual tool dan komponen transmisi dari deformasi",
          priority: "segera",
          estimatedMinutes: 20,
        },
        {
          id: "osf-3",
          text: "Ganti tool bila tool wear melebihi 200 menit",
          priority: "terjadwal",
          estimatedMinutes: 30,
        },
        {
          id: "osf-4",
          text: "Kalibrasi ulang beban kerja mesin sesuai spesifikasi",
          priority: "terjadwal",
          estimatedMinutes: 25,
        },
      ],
    },
    downtime: {
      costPerHourIdr: 10_000_000,
      estimatedRepairHours: 3,
      projections: [
        { delayHours: 24, additionalLossIdr: 240_000_000 },
        { delayHours: 48, additionalLossIdr: 480_000_000 },
      ],
    },
  },
  twf: {
    key: "twf",
    responseText:
      "Model mendeteksi indikasi Tool Wear Failure (TWF) dengan probabilitas 74%. Tool wear sudah mendekati batas usia pakai sehingga risiko kegagalan meningkat. Jadwalkan penggantian tool sesuai rencana tindakan di bawah.",
    prediction: {
      probability: 0.74,
      label: true,
      healthScore: 26,
      riskLevel: "sedang",
    },
    shap: {
      contributions: [
        { feature: "Tool wear [min]", value: 0.45 },
        { feature: "Torsi [Nm]", value: 0.11 },
        { feature: "Tipe mesin (L)", value: 0.06 },
        { feature: "Suhu proses [K]", value: -0.03 },
        { feature: "Kecepatan putar [rpm]", value: -0.02 },
      ],
    },
    sop: {
      title: "Penanganan Tool Wear Failure",
      steps: [
        {
          id: "twf-1",
          text: "Hentikan proses pada titik aman berikutnya (akhir siklus)",
          priority: "segera",
          estimatedMinutes: 10,
        },
        {
          id: "twf-2",
          text: "Ganti tool dengan unit baru dan reset counter tool wear",
          priority: "segera",
          estimatedMinutes: 25,
        },
        {
          id: "twf-3",
          text: "Periksa kualitas output batch terakhir dari cacat",
          priority: "terjadwal",
          estimatedMinutes: 15,
        },
        {
          id: "twf-4",
          text: "Evaluasi interval penggantian tool pada jadwal preventif",
          priority: "terjadwal",
          estimatedMinutes: 20,
        },
      ],
    },
    downtime: {
      costPerHourIdr: 8_000_000,
      estimatedRepairHours: 2,
      projections: [
        { delayHours: 24, additionalLossIdr: 192_000_000 },
        { delayHours: 48, additionalLossIdr: 384_000_000 },
      ],
    },
  },
  pwf: {
    key: "pwf",
    responseText:
      "Terdeteksi indikasi Power Failure (PWF) dengan probabilitas 69%. Kombinasi kecepatan putar rendah dengan torsi saat ini membuat daya keluar dari rentang operasi aman (3.500-9.000 W). Periksa suplai daya dan parameter operasi sesuai rencana di bawah.",
    prediction: {
      probability: 0.69,
      label: true,
      healthScore: 31,
      riskLevel: "sedang",
    },
    shap: {
      contributions: [
        { feature: "Kecepatan putar [rpm]", value: 0.36 },
        { feature: "Torsi [Nm]", value: 0.22 },
        { feature: "Tool wear [min]", value: 0.04 },
        { feature: "Suhu proses [K]", value: -0.06 },
        { feature: "Suhu udara [K]", value: -0.02 },
      ],
    },
    sop: {
      title: "Penanganan Power Failure",
      steps: [
        {
          id: "pwf-1",
          text: "Periksa suplai daya dan koneksi kelistrikan mesin",
          priority: "segera",
          estimatedMinutes: 10,
        },
        {
          id: "pwf-2",
          text: "Verifikasi kecepatan putar dan torsi berada dalam rentang daya 3.500-9.000 W",
          priority: "segera",
          estimatedMinutes: 15,
        },
        {
          id: "pwf-3",
          text: "Inspeksi motor drive dan inverter dari anomali",
          priority: "terjadwal",
          estimatedMinutes: 40,
        },
        {
          id: "pwf-4",
          text: "Jadwalkan pengujian beban penuh setelah normalisasi",
          priority: "terjadwal",
          estimatedMinutes: 20,
        },
      ],
    },
    downtime: {
      costPerHourIdr: 9_500_000,
      estimatedRepairHours: 3,
      projections: [
        { delayHours: 24, additionalLossIdr: 228_000_000 },
        { delayHours: 48, additionalLossIdr: 456_000_000 },
      ],
    },
  },
  none: {
    key: "none",
    responseText:
      "Kabar baik: berdasarkan parameter tersebut, mesin diprediksi beroperasi normal dengan probabilitas kegagalan hanya 3%. Tidak ada tindakan darurat yang diperlukan; lanjutkan pemantauan rutin dan pastikan parameter tetap dalam rentang operasi normal.",
    prediction: {
      probability: 0.03,
      label: false,
      healthScore: 97,
      riskLevel: "rendah",
    },
  },
};
