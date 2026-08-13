"use server";

import { backendFetch } from "@/lib/backend-fetch";
import type { ReportData } from "@/lib/types";

interface ReportApiOut {
  sensor: {
    id: string;
    reading_timestamp: string;
    air_temperature_k: number;
    process_temperature_k: number;
    rotational_speed_rpm: number;
    tool_wear_min: number;
  };
  prediction: {
    id: string;
    predicted_label: boolean;
    failure_probability: number;
    health_score: number;
    model_version: string;
    threshold: number;
  };
  shap: {
    base_value: number;
    features: {
      feature_name: string;
      value: number;
      shap_value: number;
      rank: number;
    }[];
  };
  recommendations: {
    nearest_failure: {
      distances: number[];
      rows: Record<string, number | boolean>[];
    };
    nearest_no_failure: {
      distances: number[];
      rows: Record<string, number | boolean>[];
    };
    worst_case_delta: {
      nearest_safe_point: Record<string, number | boolean> | null;
      suggested_adjustments: Record<string, number>;
    };
  };
  root_cause: {
    query: string;
    answer: string;
    used_web_fallback: boolean;
    retrieved_chunk_ids: string[];
    retrieved_chunks: {
      chunk_id: string;
      doc_name: string | null;
      heading_1: string | null;
      heading_2: string | null;
      content: string;
    }[];
  } | null;
  part_prices: {
    part_name: string;
    price_min: number | null;
    price_max: number | null;
    currency: string;
    source_url: string | null;
  }[];
  final_report_text: string;
  llm_model: string;
  created_at: string;
}

function fromApiNeighborRow(row: Record<string, number | boolean>) {
  return {
    airTemperatureK: Number(row.air_temperature_k),
    processTemperatureK: Number(row.process_temperature_k),
    rotationalSpeedRpm: Number(row.rotational_speed_rpm),
    toolWearMin: Number(row.tool_wear_min),
    machineFailure: Boolean(row.machine_failure),
  };
}

function fromApi(r: ReportApiOut): ReportData {
  return {
    sensor: {
      id: r.sensor.id,
      readingTimestamp: r.sensor.reading_timestamp,
      airTemperatureK: r.sensor.air_temperature_k,
      processTemperatureK: r.sensor.process_temperature_k,
      rotationalSpeedRpm: r.sensor.rotational_speed_rpm,
      toolWearMin: r.sensor.tool_wear_min,
    },
    prediction: {
      id: r.prediction.id,
      predictedLabel: r.prediction.predicted_label,
      failureProbability: r.prediction.failure_probability,
      healthScore: r.prediction.health_score,
      modelVersion: r.prediction.model_version,
      threshold: r.prediction.threshold,
    },
    shap: {
      baseValue: r.shap.base_value,
      features: r.shap.features.map((f) => ({
        featureName: f.feature_name,
        value: f.value,
        shapValue: f.shap_value,
        rank: f.rank,
      })),
    },
    recommendations: {
      nearestFailure: {
        distances: r.recommendations.nearest_failure.distances,
        rows: r.recommendations.nearest_failure.rows.map(fromApiNeighborRow),
      },
      nearestNoFailure: {
        distances: r.recommendations.nearest_no_failure.distances,
        rows: r.recommendations.nearest_no_failure.rows.map(
          fromApiNeighborRow,
        ),
      },
      worstCaseDelta: {
        nearestSafePoint:
          r.recommendations.worst_case_delta.nearest_safe_point,
        suggestedAdjustments:
          r.recommendations.worst_case_delta.suggested_adjustments,
      },
    },
    rootCause: r.root_cause
      ? {
          query: r.root_cause.query,
          answer: r.root_cause.answer,
          usedWebFallback: r.root_cause.used_web_fallback,
          retrievedChunkIds: r.root_cause.retrieved_chunk_ids,
          retrievedChunks: r.root_cause.retrieved_chunks.map((c) => ({
            chunkId: c.chunk_id,
            docName: c.doc_name ?? undefined,
            heading1: c.heading_1 ?? undefined,
            heading2: c.heading_2 ?? undefined,
            content: c.content,
          })),
        }
      : null,
    partPrices: r.part_prices.map((p) => ({
      partName: p.part_name,
      priceMin: p.price_min,
      priceMax: p.price_max,
      currency: p.currency,
      sourceUrl: p.source_url,
    })),
    finalReportText: r.final_report_text,
    llmModel: r.llm_model,
    createdAt: r.created_at,
  };
}

export async function getReportAction(
  machineId: string,
): Promise<ReportData | null> {
  const resp = await backendFetch(
    `/report/latest?machine_id=${encodeURIComponent(machineId)}`,
    { cache: "no-store" },
  );
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new Error(`Gagal memuat laporan (${resp.status})`);
  }
  const data = (await resp.json()) as ReportApiOut;
  return fromApi(data);
}
