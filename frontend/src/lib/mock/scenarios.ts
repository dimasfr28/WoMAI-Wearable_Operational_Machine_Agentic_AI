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

export const MANUAL_PREFIX = "Manual machine parameter input";

export function formatManualMessage(p: ManualParams): string {
  return (
    `${MANUAL_PREFIX} - Type: ${p.type}, Air temp: ${p.airTemp} K, ` +
    `Process temp: ${p.processTemp} K, Rotational speed: ${p.rpm} rpm, ` +
    `Torque: ${p.torque} Nm, Tool wear: ${p.toolWear} min`
  );
}

export function parseManualInput(text: string): ManualParams | null {
  if (!text.startsWith(MANUAL_PREFIX)) return null;
  const type = /Type:\s*([LMH])/.exec(text)?.[1];
  const airTemp = /Air temp:\s*([\d.]+)/.exec(text)?.[1];
  const processTemp = /Process temp:\s*([\d.]+)/.exec(text)?.[1];
  const rpm = /Rotational speed:\s*([\d.]+)/.exec(text)?.[1];
  const torque = /Torque:\s*([\d.]+)/.exec(text)?.[1];
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
  ["hdf", ["temperature", "hot", "heat", "overheat"]],
  ["osf", ["torque", "load", "overstrain"]],
  ["twf", ["worn", "tool wear", "wear"]],
  ["pwf", ["power", "electrical", "voltage"]],
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
      "Based on the parameters you described, the model detects signs of Heat Dissipation Failure (HDF) with 87% probability. The main drivers are a high process temperature and a narrowing air-process temperature gap, which makes heat dissipation ineffective. I've prepared an action plan below — prioritize the steps marked Urgent, and note the estimated loss if repairs are delayed.",
    prediction: {
      probability: 0.87,
      label: true,
      healthScore: 13,
      riskLevel: "tinggi",
    },
    shap: {
      contributions: [
        { feature: "Process temperature [K]", value: 0.34 },
        { feature: "Air-process temperature difference", value: 0.21 },
        { feature: "Rotational speed [rpm]", value: 0.12 },
        { feature: "Torque [Nm]", value: 0.05 },
        { feature: "Machine type (M)", value: -0.04 },
      ],
    },
    sop: {
      title: "Heat Dissipation Failure Handling",
      steps: [
        {
          id: "hdf-1",
          text: "Reduce machine load to ≤50% and monitor the process temperature trend",
          priority: "segera",
          estimatedMinutes: 10,
        },
        {
          id: "hdf-2",
          text: "Inspect and clean the cooling system (fan, heatsink, air ducts)",
          priority: "segera",
          estimatedMinutes: 15,
        },
        {
          id: "hdf-3",
          text: "Measure the air-process temperature difference; confirm it's back above 8.6 K",
          priority: "segera",
          estimatedMinutes: 20,
        },
        {
          id: "hdf-4",
          text: "Perform a full thermal inspection of the bearing and gearbox",
          priority: "terjadwal",
          estimatedMinutes: 45,
        },
        {
          id: "hdf-5",
          text: "Log the incident in the maintenance log and schedule a re-check in 24 hours",
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
      "The parameters indicate signs of Overstrain Failure (OSF) with 82% probability. The combination of high torque and accumulated tool wear is pushing the load past the material's safe threshold. Follow the action plan below and reduce the load temporarily before inspection.",
    prediction: {
      probability: 0.82,
      label: true,
      healthScore: 18,
      riskLevel: "tinggi",
    },
    shap: {
      contributions: [
        { feature: "Torque [Nm]", value: 0.38 },
        { feature: "Tool wear [min]", value: 0.27 },
        { feature: "Machine type (L)", value: 0.09 },
        { feature: "Process temperature [K]", value: -0.05 },
        { feature: "Rotational speed [rpm]", value: -0.08 },
      ],
    },
    sop: {
      title: "Overstrain Failure Handling",
      steps: [
        {
          id: "osf-1",
          text: "Reduce operating torque below the material type's safe threshold",
          priority: "segera",
          estimatedMinutes: 5,
        },
        {
          id: "osf-2",
          text: "Visually inspect the tool and transmission components for deformation",
          priority: "segera",
          estimatedMinutes: 20,
        },
        {
          id: "osf-3",
          text: "Replace the tool if tool wear exceeds 200 minutes",
          priority: "terjadwal",
          estimatedMinutes: 30,
        },
        {
          id: "osf-4",
          text: "Recalibrate the machine's working load to spec",
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
      "The model detects signs of Tool Wear Failure (TWF) with 74% probability. Tool wear is approaching its end-of-life threshold, raising the risk of failure. Schedule a tool replacement per the action plan below.",
    prediction: {
      probability: 0.74,
      label: true,
      healthScore: 26,
      riskLevel: "sedang",
    },
    shap: {
      contributions: [
        { feature: "Tool wear [min]", value: 0.45 },
        { feature: "Torque [Nm]", value: 0.11 },
        { feature: "Machine type (L)", value: 0.06 },
        { feature: "Process temperature [K]", value: -0.03 },
        { feature: "Rotational speed [rpm]", value: -0.02 },
      ],
    },
    sop: {
      title: "Tool Wear Failure Handling",
      steps: [
        {
          id: "twf-1",
          text: "Stop the process at the next safe point (end of cycle)",
          priority: "segera",
          estimatedMinutes: 10,
        },
        {
          id: "twf-2",
          text: "Replace the tool with a new unit and reset the tool wear counter",
          priority: "segera",
          estimatedMinutes: 25,
        },
        {
          id: "twf-3",
          text: "Check the last batch's output quality for defects",
          priority: "terjadwal",
          estimatedMinutes: 15,
        },
        {
          id: "twf-4",
          text: "Review the tool replacement interval in the preventive maintenance schedule",
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
      "Signs of Power Failure (PWF) detected with 69% probability. The combination of low rotational speed and the current torque is pushing power outside the safe operating range (3,500-9,000 W). Check the power supply and operating parameters per the plan below.",
    prediction: {
      probability: 0.69,
      label: true,
      healthScore: 31,
      riskLevel: "sedang",
    },
    shap: {
      contributions: [
        { feature: "Rotational speed [rpm]", value: 0.36 },
        { feature: "Torque [Nm]", value: 0.22 },
        { feature: "Tool wear [min]", value: 0.04 },
        { feature: "Process temperature [K]", value: -0.06 },
        { feature: "Air temperature [K]", value: -0.02 },
      ],
    },
    sop: {
      title: "Power Failure Handling",
      steps: [
        {
          id: "pwf-1",
          text: "Check the machine's power supply and electrical connections",
          priority: "segera",
          estimatedMinutes: 10,
        },
        {
          id: "pwf-2",
          text: "Verify rotational speed and torque are within the 3,500-9,000 W power range",
          priority: "segera",
          estimatedMinutes: 15,
        },
        {
          id: "pwf-3",
          text: "Inspect the drive motor and inverter for anomalies",
          priority: "terjadwal",
          estimatedMinutes: 40,
        },
        {
          id: "pwf-4",
          text: "Schedule a full-load test after normalization",
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
      "Good news: based on those parameters, the machine is predicted to operate normally, with only a 3% failure probability. No emergency action is needed — continue routine monitoring and keep the parameters within the normal operating range.",
    prediction: {
      probability: 0.03,
      label: false,
      healthScore: 97,
      riskLevel: "rendah",
    },
  },
};
