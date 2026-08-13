# Report Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/report` page to the Next.js frontend that displays the AI's full structured output (health score, failure risk, SHAP, worst-case delta, KNN similar cases, root-cause analysis, part prices, final report) for one machine's latest report — with zero new backend logic.

**Architecture:** A new `"use server"` action wraps the already-existing `GET /report/latest?machine_id=` endpoint and maps its snake_case JSON to a new camelCase `ReportData` frontend type. A new client page reads an optional `?machine_id=` query param (falling back to the first machine in the list), renders the mapped data as a set of cards, and shows "N/A"/"Belum ada laporan" placeholders when no report exists yet for that machine. Reachable via a new sidebar nav item and a contextual link next to the chat's machine picker.

**Tech Stack:** Next.js 16 App Router, TypeScript, shadcn/ui, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-14-report-page-design.md`

## Global Constraints

- Zero backend changes — every field this plan renders comes from the existing `ReportOut` schema (`backend/app/schemas/report.py`), reached via the existing `GET /report/latest?machine_id=<uuid>` endpoint (`backend/app/api/routes_report.py`). No route, schema, or pipeline code is touched.
- No Dashboard page, no sparkline/live monitoring, no auto-refresh/polling — this page is a static-per-visit detail view of one report, with a manual refresh button only.
- On a 404 from `GET /report/latest` (no sensor reading/prediction exists yet for that machine), the page must render "N/A"/"Belum ada laporan" — never a blank page or an unhandled error screen.
- Route: `/report` (page title in the UI: "Laporan"), optional query param `?machine_id=<uuid>` to pre-select a machine; without it, default to the first machine returned by `useMachines()`.
- `recommendations.nearest_failure`/`nearest_no_failure` row shape (from `backend/app/ml/knn_tool.py`): `{air_temperature_k, process_temperature_k, rotational_speed_rpm, tool_wear_min, machine_failure}`. `recommendations.worst_case_delta.suggested_adjustments` keys are **display names** (e.g. `"Rotational speed rpm"`), not snake_case raw field names — map them as opaque string keys, do not attempt to re-map them to camelCase.

---

### Task 1: Frontend — `ReportData` type and `getReportAction`

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Create: `frontend/src/app/actions/report.ts`
- Create: `frontend/src/app/actions/report.test.ts`

**Interfaces:**
- Produces: `ReportData` interface (and its nested `ReportSensorSnapshot`, `ReportPrediction`, `ReportShap`, `ReportShapFeature`, `ReportNeighborRow`, `ReportNeighborGroup`, `ReportRecommendations`, `ReportRetrievedChunk`, `ReportRootCause`, `ReportPartPrice` interfaces) in `frontend/src/lib/types.ts`. `getReportAction(machineId: string): Promise<ReportData | null>` in `frontend/src/app/actions/report.ts` — Task 2 imports and calls this directly from a Client Component (Next.js Server Actions are directly callable from Client Components, same as every other action in this codebase).

- [ ] **Step 1: Add `ReportData` and its nested types**

In `frontend/src/lib/types.ts`, find:
```ts
export interface ChatSession {
```
Insert immediately BEFORE that line (i.e. after the existing `Sop` interface, before `ChatSession`):
```ts
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

export interface ReportData {
  sensor: ReportSensorSnapshot;
  prediction: ReportPrediction;
  shap: ReportShap;
  recommendations: ReportRecommendations;
  rootCause: ReportRootCause | null;
  partPrices: ReportPartPrice[];
  finalReportText: string;
  llmModel: string;
  createdAt: string; // ISO
}

export interface ChatSession {
```
(Note: the last line above is the pre-existing `export interface ChatSession {` line — you are inserting new content directly above it, not replacing it. The rest of `ChatSession`'s body is unchanged.)

- [ ] **Step 2: Write the failing test for `getReportAction`**

Create `frontend/src/app/actions/report.test.ts`:
```ts
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

  it("throws on a non-ok, non-404 status", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 500));
    await expect(getReportAction("m-1")).rejects.toThrow(
      "Gagal memuat laporan (500)",
    );
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && bun run test app/actions/report.test.ts`
Expected: FAIL — `./report` module not found.

- [ ] **Step 4: Implement `getReportAction`**

Create `frontend/src/app/actions/report.ts`:
```ts
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && bun run test app/actions/report.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full test suite**

Run: `cd frontend && bun run test`
Expected: all suites pass, including pre-existing ones.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/app/actions/report.ts frontend/src/app/actions/report.test.ts
git commit -m "feat(frontend): add ReportData type and getLatestReport action"
```

---

### Task 2: Frontend — Report page

**Files:**
- Create: `frontend/src/app/(app)/report/page.tsx`

**Interfaces:**
- Consumes: `getReportAction(machineId: string): Promise<ReportData | null>` from Task 1's `frontend/src/app/actions/report.ts`; `ReportData` and nested types from Task 1's `frontend/src/lib/types.ts`; `useMachines()` from `frontend/src/hooks/use-machines.ts` (returns `{ machines: Machine[], loading: boolean }`); `formatRupiah(amount: number): string` from `frontend/src/lib/format.ts`; `RISK_BADGE: Record<RiskLevel, string>` from `frontend/src/lib/risk.ts`.

- [ ] **Step 1: Create the Report page**

Create `frontend/src/app/(app)/report/page.tsx`:
```tsx
"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { unstable_rethrow, useSearchParams } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { getReportAction } from "@/app/actions/report";
import { useMachines } from "@/hooks/use-machines";
import { formatRupiah } from "@/lib/format";
import { RISK_BADGE } from "@/lib/risk";
import type { ReportData, RiskLevel } from "@/lib/types";
import { cn } from "@/lib/utils";

function riskLevelFor(probability: number): RiskLevel {
  if (probability < 0.3) return "rendah";
  if (probability < 0.6) return "sedang";
  return "tinggi";
}

function ReportContent() {
  const searchParams = useSearchParams();
  const { machines } = useMachines();
  const [machineId, setMachineId] = useState<string | null>(
    searchParams.get("machine_id"),
  );
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!machineId && machines.length > 0) {
      setMachineId(machines[0].id);
    }
  }, [machineId, machines]);

  const load = useCallback(async () => {
    if (!machineId) return;
    setLoading(true);
    try {
      const data = await getReportAction(machineId);
      setReport(data);
    } catch (err) {
      unstable_rethrow(err);
      toast.error(
        err instanceof Error ? err.message : "Gagal memuat laporan.",
      );
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [machineId]);

  useEffect(() => {
    load();
  }, [load]);

  const selectedMachine = machines.find((m) => m.id === machineId);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Laporan</h1>
          <p className="text-sm text-muted-foreground">
            Laporan AI terakhir untuk satu mesin.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={machineId ?? ""}
            onValueChange={(v) => setMachineId(v || null)}
          >
            <SelectTrigger className="w-[180px]">
              <span
                data-slot="select-value"
                className={cn(
                  "flex flex-1 truncate text-left",
                  !selectedMachine && "text-muted-foreground",
                )}
              >
                {selectedMachine?.name ?? "Pilih mesin"}
              </span>
            </SelectTrigger>
            <SelectContent>
              {machines.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="icon"
            onClick={load}
            disabled={loading || !machineId}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            <span className="sr-only">Refresh</span>
          </Button>
        </div>
      </div>

      {!machineId && loaded && (
        <p className="text-sm text-muted-foreground">
          Belum ada mesin terdaftar.
        </p>
      )}

      {machineId && (
        <>
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Health Score
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold tabular-nums">
                  {report ? (
                    <>
                      {Math.round(report.prediction.healthScore)}
                      <span className="text-base font-normal text-muted-foreground">
                        /100
                      </span>
                    </>
                  ) : (
                    <span className="text-muted-foreground">N/A</span>
                  )}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Failure Risk
                </CardTitle>
              </CardHeader>
              <CardContent>
                {report ? (
                  <>
                    <div className="text-3xl font-bold tabular-nums">
                      {(report.prediction.failureProbability * 100).toFixed(
                        1,
                      )}
                      %
                    </div>
                    <Badge
                      className={cn(
                        "mt-1",
                        RISK_BADGE[
                          riskLevelFor(report.prediction.failureProbability)
                        ],
                      )}
                    >
                      Risiko{" "}
                      {riskLevelFor(report.prediction.failureProbability)}{" "}
                      (threshold {(report.prediction.threshold * 100).toFixed(
                        1,
                      )}
                      %)
                    </Badge>
                  </>
                ) : (
                  <div className="text-3xl font-bold text-muted-foreground">
                    N/A
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {!report && loaded ? (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                Belum ada laporan untuk mesin ini.
              </CardContent>
            </Card>
          ) : report ? (
            <>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Sensor Terbaru
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <table className="w-full text-sm">
                    <tbody>
                      <tr className="border-b">
                        <td className="py-1.5 text-muted-foreground">
                          Air Temperature
                        </td>
                        <td className="py-1.5 text-right tabular-nums">
                          {report.sensor.airTemperatureK} K
                        </td>
                      </tr>
                      <tr className="border-b">
                        <td className="py-1.5 text-muted-foreground">
                          Process Temperature
                        </td>
                        <td className="py-1.5 text-right tabular-nums">
                          {report.sensor.processTemperatureK} K
                        </td>
                      </tr>
                      <tr className="border-b">
                        <td className="py-1.5 text-muted-foreground">
                          Rotational Speed
                        </td>
                        <td className="py-1.5 text-right tabular-nums">
                          {report.sensor.rotationalSpeedRpm} rpm
                        </td>
                      </tr>
                      <tr>
                        <td className="py-1.5 text-muted-foreground">
                          Tool Wear
                        </td>
                        <td className="py-1.5 text-right tabular-nums">
                          {report.sensor.toolWearMin} min
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  <div className="mt-3 flex items-center gap-2">
                    <Badge
                      variant={
                        report.prediction.predictedLabel
                          ? "destructive"
                          : "secondary"
                      }
                    >
                      {report.prediction.predictedLabel
                        ? "FAILURE DIPREDIKSI"
                        : "NORMAL"}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      model: {report.prediction.modelVersion}
                    </span>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    SHAP — Fitur Paling Berpengaruh
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  {report.shap.features.map((f) => {
                    const max = Math.max(
                      ...report.shap.features.map((x) =>
                        Math.abs(x.shapValue),
                      ),
                      0.0001,
                    );
                    const positive = f.shapValue >= 0;
                    return (
                      <div
                        key={f.featureName}
                        className="flex items-center gap-3 text-sm"
                      >
                        <span className="w-32 shrink-0 truncate">
                          {f.featureName}
                        </span>
                        <div className="h-3 flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn(
                              "h-full rounded-full",
                              positive ? "bg-red-400" : "bg-emerald-400",
                            )}
                            style={{
                              width: `${(Math.abs(f.shapValue) / max) * 100}%`,
                            }}
                          />
                        </div>
                        <span className="w-16 shrink-0 text-right tabular-nums text-muted-foreground">
                          {positive ? "+" : ""}
                          {(f.shapValue * 100).toFixed(2)}%
                        </span>
                      </div>
                    );
                  })}
                  <p className="pt-1 text-xs text-muted-foreground">
                    base value: {(report.shap.baseValue * 100).toFixed(2)}%
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Worst-Case Delta
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {Object.keys(
                    report.recommendations.worstCaseDelta
                      .suggestedAdjustments,
                  ).length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Belum cukup data historis untuk menghitung rekomendasi.
                    </p>
                  ) : (
                    <ul className="list-disc space-y-1 pl-5 text-sm">
                      {Object.entries(
                        report.recommendations.worstCaseDelta
                          .suggestedAdjustments,
                      ).map(([feature, value]) => (
                        <li key={feature}>
                          {feature}: {value >= 0 ? "+" : ""}
                          {value} (menuju titik aman terdekat)
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Kasus Serupa (KNN)
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="mb-1 text-xs font-medium">
                      Nearest Failure
                    </p>
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-muted-foreground">
                          <th className="text-left font-normal">Air T</th>
                          <th className="text-left font-normal">Proc T</th>
                          <th className="text-left font-normal">RPM</th>
                          <th className="text-left font-normal">Wear</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.recommendations.nearestFailure.rows.length ===
                        0 ? (
                          <tr>
                            <td
                              colSpan={4}
                              className="py-1 text-muted-foreground"
                            >
                              tidak ada data
                            </td>
                          </tr>
                        ) : (
                          report.recommendations.nearestFailure.rows.map(
                            (r, i) => (
                              <tr key={i}>
                                <td>{r.airTemperatureK}</td>
                                <td>{r.processTemperatureK}</td>
                                <td>{r.rotationalSpeedRpm}</td>
                                <td>{r.toolWearMin}</td>
                              </tr>
                            ),
                          )
                        )}
                      </tbody>
                    </table>
                  </div>
                  <div>
                    <p className="mb-1 text-xs font-medium">
                      Nearest No-Failure
                    </p>
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-muted-foreground">
                          <th className="text-left font-normal">Air T</th>
                          <th className="text-left font-normal">Proc T</th>
                          <th className="text-left font-normal">RPM</th>
                          <th className="text-left font-normal">Wear</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.recommendations.nearestNoFailure.rows
                          .length === 0 ? (
                          <tr>
                            <td
                              colSpan={4}
                              className="py-1 text-muted-foreground"
                            >
                              tidak ada data
                            </td>
                          </tr>
                        ) : (
                          report.recommendations.nearestNoFailure.rows.map(
                            (r, i) => (
                              <tr key={i}>
                                <td>{r.airTemperatureK}</td>
                                <td>{r.processTemperatureK}</td>
                                <td>{r.rotationalSpeedRpm}</td>
                                <td>{r.toolWearMin}</td>
                              </tr>
                            ),
                          )
                        )}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>

              {report.rootCause && (
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="text-sm font-medium text-muted-foreground">
                        Root Cause Analysis
                      </CardTitle>
                      <Badge variant="outline">
                        {report.rootCause.usedWebFallback
                          ? "sumber: web (fallback)"
                          : "sumber: knowledgebase"}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="mb-2 text-xs text-muted-foreground">
                      query: {report.rootCause.query}
                    </p>
                    <div className="text-sm whitespace-pre-wrap">
                      {report.rootCause.answer}
                    </div>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Estimasi Harga Part
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {report.partPrices.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Tidak ada listing e-commerce yang ditemukan untuk part
                      ini saat laporan dibuat.
                    </p>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-muted-foreground">
                          <th className="text-left font-normal">Part</th>
                          <th className="text-left font-normal">Harga</th>
                          <th className="text-left font-normal">Sumber</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.partPrices.map((p, i) => (
                          <tr key={i} className="border-t">
                            <td className="py-1.5">{p.partName}</td>
                            <td className="py-1.5">
                              {p.priceMin != null && p.priceMax != null
                                ? p.priceMin === p.priceMax
                                  ? formatRupiah(p.priceMin)
                                  : `${formatRupiah(p.priceMin)} - ${formatRupiah(p.priceMax)}`
                                : "tidak ditemukan"}
                            </td>
                            <td className="py-1.5">
                              {p.sourceUrl ? (
                                <a
                                  href={p.sourceUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-primary underline"
                                >
                                  link
                                </a>
                              ) : (
                                "-"
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Laporan Akhir
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-sm whitespace-pre-wrap">
                    {report.finalReportText}
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground">
                    model: {report.llmModel}
                  </p>
                </CardContent>
              </Card>
            </>
          ) : null}
        </>
      )}
    </div>
  );
}

export default function ReportPage() {
  return (
    <Suspense fallback={null}>
      <ReportContent />
    </Suspense>
  );
}
```

- [ ] **Step 2: Run the frontend gate**

Run: `cd frontend && bunx tsc --noEmit && bun run lint && bun run build`
Expected: all pass, `/report` appears in the build's route list.

- [ ] **Step 3: Commit**

```bash
git add "frontend/src/app/(app)/report/page.tsx"
git commit -m "feat(frontend): add Report page for one machine's latest AI report"
```

---

### Task 3: Frontend — sidebar nav item and chat contextual link

**Files:**
- Modify: `frontend/src/components/app-sidebar.tsx`
- Modify: `frontend/src/components/chat/chat-input.tsx`

**Interfaces:**
- Consumes: `/report` route from Task 2 (no exported interface — this task only adds navigation links to it).

- [ ] **Step 1: Add the sidebar nav item**

In `frontend/src/components/app-sidebar.tsx`, find:
```tsx
import {
  Factory,
  FileText,
  History,
  LogOut,
  MessageSquarePlus,
} from "lucide-react";
```
Replace with:
```tsx
import {
  Factory,
  FileBarChart,
  FileText,
  History,
  LogOut,
  MessageSquarePlus,
} from "lucide-react";
```
Then find:
```tsx
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Riwayat"
                  isActive={pathname === "/riwayat"}
                  render={<Link href="/riwayat" onClick={closeOnMobile} />}
                >
                  <History />
                  <span>Riwayat</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
```
Replace with:
```tsx
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Riwayat"
                  isActive={pathname === "/riwayat"}
                  render={<Link href="/riwayat" onClick={closeOnMobile} />}
                >
                  <History />
                  <span>Riwayat</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Laporan"
                  isActive={pathname === "/report"}
                  render={<Link href="/report" onClick={closeOnMobile} />}
                >
                  <FileBarChart />
                  <span>Laporan</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
```

- [ ] **Step 2: Add the contextual link near the chat's machine picker**

In `frontend/src/components/chat/chat-input.tsx`, find:
```tsx
"use client";

import { useState } from "react";
import { SendHorizonal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MachinePicker } from "@/components/chat/machine-picker";
import { ManualInputDialog } from "@/components/chat/manual-input-dialog";
import type { Machine } from "@/lib/types";
```
Replace with:
```tsx
"use client";

import Link from "next/link";
import { useState } from "react";
import { SendHorizonal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MachinePicker } from "@/components/chat/machine-picker";
import { ManualInputDialog } from "@/components/chat/manual-input-dialog";
import type { Machine } from "@/lib/types";
```
Then find:
```tsx
  return (
    <div className="border-t bg-background p-4">
      <form
        className="mx-auto flex w-full max-w-3xl items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
```
Replace with:
```tsx
  return (
    <div className="border-t bg-background p-4">
      {machine && (
        <div className="mx-auto mb-2 flex w-full max-w-3xl justify-end">
          <Button
            variant="ghost"
            size="sm"
            className="h-auto p-0 text-xs text-muted-foreground hover:text-foreground"
            render={<Link href={`/report?machine_id=${machine.id}`} />}
          >
            Lihat laporan lengkap →
          </Button>
        </div>
      )}
      <form
        className="mx-auto flex w-full max-w-3xl items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
```

- [ ] **Step 3: Run the frontend gate**

Run: `cd frontend && bunx tsc --noEmit && bun run lint && bun run build && bun run test`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/app-sidebar.tsx frontend/src/components/chat/chat-input.tsx
git commit -m "feat(frontend): link to the Report page from the sidebar and chat"
```

---

### Task 4: Verification

**Files:** none (verification only).

- [ ] **Step 1: Full frontend gate**

Run: `cd frontend && bunx tsc --noEmit && bun run lint && bun run build && bun run test`
Expected: all four pass, `/report` listed among the build's routes.

- [ ] **Step 2: Confirm zero backend changes**

Run: `git diff --stat <plan-base-commit>..HEAD -- backend/`
Expected: no output (empty diff) — this plan must not touch `backend/` at all.

- [ ] **Step 3: Manual E2E (if a live environment is available)**

- Open `/report` directly (no query param) → defaults to the first machine in the list.
- Pick a machine that has a completed report → all 8 cards render with real data, Health Score and Failure Risk show real numbers (not "N/A").
- Pick a machine with no sensor reading/prediction yet → Health Score and Failure Risk show "N/A", and a single "Belum ada laporan untuk mesin ini." card appears instead of the other 6 sections.
- From `/chat`, select a machine in the `MachinePicker` → confirm "Lihat laporan lengkap →" appears above the input, and clicking it navigates to `/report?machine_id=<the same machine>` with that machine pre-selected.
- Confirm the sidebar's "Laporan" item is present (after "Riwayat") and highlights as active when on `/report`.

If no live environment is available, report that plainly — Steps 1-2 remain the required minimum bar for this task.

- [ ] **Step 4: Report findings**

No commit for this task (verification only) — report the results from Steps 1-3.
