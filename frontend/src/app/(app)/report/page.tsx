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
      // eslint-disable-next-line react-hooks/set-state-in-effect -- defaults machineId once machines load; not derivable via render since it must remain user-overridable state
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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount/on-machineId-change is the intended data-loading pattern here
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
