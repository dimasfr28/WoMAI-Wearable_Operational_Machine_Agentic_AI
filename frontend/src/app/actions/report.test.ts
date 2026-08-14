import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/backend-fetch", () => ({
  backendFetch: vi.fn(),
}));

import { backendFetch } from "@/lib/backend-fetch";
import { getReportAction } from "./report";

const mockedBackendFetch = vi.mocked(backendFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SAMPLE_REPORT = {
  sensor: {
    id: "sr-1",
    reading_timestamp: "2026-08-14T00:00:00Z",
    air_temperature_k: 298.9,
    process_temperature_k: 309.1,
    rotational_speed_rpm: 2861,
    tool_wear_min: 143,
  },
  prediction: {
    id: "pred-1",
    predicted_label: true,
    failure_probability: 0.993,
    health_score: 1,
    model_version: "best_model.pkl-ec0a09ddf31e",
    threshold: 0.503,
  },
  shap: {
    base_value: 0.0263,
    features: [
      {
        feature_name: "Rotational speed rpm",
        value: 2861,
        shap_value: 0.7534,
        rank: 1,
      },
    ],
  },
  recommendations: {
    nearest_failure: {
      distances: [0.1],
      rows: [
        {
          air_temperature_k: 298.9,
          process_temperature_k: 309.1,
          rotational_speed_rpm: 2861,
          tool_wear_min: 143,
          machine_failure: true,
        },
      ],
    },
    nearest_no_failure: {
      distances: [0.2],
      rows: [
        {
          air_temperature_k: 298.3,
          process_temperature_k: 308.1,
          rotational_speed_rpm: 2636,
          tool_wear_min: 84,
          machine_failure: false,
        },
      ],
    },
    worst_case_delta: {
      nearest_safe_point: { air_temperature_k: 298.3 },
      suggested_adjustments: { "Rotational speed rpm": -225 },
    },
  },
  root_cause: {
    query: "why abnormal speed can cause machine failure",
    answer: "## Apa Masalahnya\nDiagnosis singkat...",
    used_web_fallback: true,
    retrieved_chunk_ids: [],
    retrieved_chunks: [],
  },
  part_prices: [
    {
      part_name: "Spindle bearing",
      price_min: 150000,
      price_max: 300000,
      currency: "IDR",
      source_url: "https://example.com",
    },
  ],
  ai_explanation: "Rotational speed rpm adalah faktor paling berpengaruh.",
  recommended_action: {
    feature: "Rotational speed rpm",
    current_value: 2861,
    target_value: 2636,
    why: "Menurunkan RPM mengurangi beban mekanis.",
    expected_impact: "Risiko kegagalan diperkirakan menurun.",
  },
  final_report_text: "Ringkasan laporan...",
  llm_model: "llama-3.3-70b-versatile",
  created_at: "2026-08-14T00:05:00Z",
};

describe("getReportAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("maps snake_case backend fields to camelCase ReportData", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse(SAMPLE_REPORT));
    const result = await getReportAction("m-1");
    expect(result).not.toBeNull();
    expect(result?.prediction.predictedLabel).toBe(true);
    expect(result?.prediction.healthScore).toBe(1);
    expect(result?.shap.features[0]).toEqual({
      featureName: "Rotational speed rpm",
      value: 2861,
      shapValue: 0.7534,
      rank: 1,
    });
    expect(result?.recommendations.nearestFailure.rows[0]).toEqual({
      airTemperatureK: 298.9,
      processTemperatureK: 309.1,
      rotationalSpeedRpm: 2861,
      toolWearMin: 143,
      machineFailure: true,
    });
    expect(
      result?.recommendations.worstCaseDelta.suggestedAdjustments,
    ).toEqual({ "Rotational speed rpm": -225 });
    expect(result?.rootCause?.usedWebFallback).toBe(true);
    expect(result?.partPrices[0].partName).toBe("Spindle bearing");
    expect(result?.aiExplanation).toBe(
      "Rotational speed rpm adalah faktor paling berpengaruh.",
    );
    expect(result?.recommendedAction).toEqual({
      feature: "Rotational speed rpm",
      currentValue: 2861,
      targetValue: 2636,
      why: "Menurunkan RPM mengurangi beban mekanis.",
      expectedImpact: "Risiko kegagalan diperkirakan menurun.",
    });
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/report/latest?machine_id=m-1",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("returns null on 404 (no report yet)", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 404));
    const result = await getReportAction("m-2");
    expect(result).toBeNull();
  });

  it("maps a null root_cause to null (non-failure prediction)", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({ ...SAMPLE_REPORT, root_cause: null }),
    );
    const result = await getReportAction("m-1");
    expect(result?.rootCause).toBeNull();
  });

  it("maps a null recommended_action to null (not enough historical data)", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({
        ...SAMPLE_REPORT,
        ai_explanation: null,
        recommended_action: null,
      }),
    );
    const result = await getReportAction("m-1");
    expect(result?.aiExplanation).toBeNull();
    expect(result?.recommendedAction).toBeNull();
  });

  it("throws on a non-ok, non-404 status", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 500));
    await expect(getReportAction("m-1")).rejects.toThrow(
      "Gagal memuat laporan (500)",
    );
  });
});
