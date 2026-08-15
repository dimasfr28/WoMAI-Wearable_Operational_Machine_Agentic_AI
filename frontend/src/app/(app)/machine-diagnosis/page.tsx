"use client";

import { useCallback, useEffect, useState } from "react";
import { unstable_rethrow } from "next/navigation";
import { AlertTriangle, CheckCircle2, Clock, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getReportAction } from "@/app/actions/report";
import { getMachineStatusAction } from "@/app/actions/machine-status";
import { RequireActiveMachine } from "@/components/require-active-machine";
import { cn } from "@/lib/utils";
import type { EarlyWarningItem, Machine, MachineStatus, ReportData } from "@/lib/types";

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("id-ID", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function EarlyWarningCard({ item }: { item: EarlyWarningItem }) {
  return (
    <Card
      className={cn(
        "py-3",
        item.isAnomaly &&
          "border-red-300 bg-red-50 shadow-[0_0_0_1px_rgba(220,38,38,0.15)] dark:border-red-900 dark:bg-red-950/30",
      )}
    >
      <CardContent className="flex flex-col gap-1 px-4">
        <p className="text-xs font-medium text-muted-foreground">
          {item.parameterLabel}
        </p>
        <p className="text-lg font-semibold tabular-nums">
          {item.currentValue} {item.unit}
        </p>
        {item.isAnomaly && (
          <Badge variant="destructive" className="w-fit text-[10px]">
            Outlier (IQR)
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}

function PredictionCard({ report }: { report: ReportData }) {
  const failed = report.prediction.predictedLabel;
  return (
    <Card
      className={cn(
        failed
          ? "border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/30"
          : "border-emerald-300 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/30",
      )}
    >
      <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          {failed ? (
            <AlertTriangle className="mt-0.5 size-6 shrink-0 text-red-600 dark:text-red-400" />
          ) : (
            <CheckCircle2 className="mt-0.5 size-6 shrink-0 text-emerald-600 dark:text-emerald-400" />
          )}
          <div>
            <p className="font-semibold">
              {failed ? "Failure Predicted" : "No Failure Predicted"}
            </p>
            <p className="text-sm text-muted-foreground">
              Machine health prediction based on the latest data recorded at{" "}
              {formatTimestamp(report.sensor.readingTimestamp)}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 gap-6">
          <div className="flex flex-col items-end gap-1">
            <span className="text-xs text-muted-foreground">Failure Risk</span>
            <span className="text-2xl font-bold tabular-nums">
              {(report.prediction.failureProbability * 100).toFixed(1)}%
            </span>
          </div>
          {report.horizonPrediction && (
            <div className="flex flex-col items-end gap-1">
              <span className="text-xs text-muted-foreground">
                Failure in +{report.horizonPrediction.horizonMinutes} Minute
              </span>
              <span className="text-2xl font-bold tabular-nums">
                {(report.horizonPrediction.failureProbability * 100).toFixed(1)}
                %
              </span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function MachineDiagnosisContent({ machine }: { machine: Machine }) {
  const [report, setReport] = useState<ReportData | null>(null);
  const [status, setStatus] = useState<MachineStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reportData, statusData] = await Promise.all([
        getReportAction(machine.id),
        getMachineStatusAction(machine.id),
      ]);
      setReport(reportData);
      setStatus(statusData);
    } catch (err) {
      unstable_rethrow(err);
      toast.error(err instanceof Error ? err.message : "Gagal memuat diagnosis.");
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [machine.id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount/on-machine-change
    load();
  }, [load]);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Machine Diagnosis</h1>
          <p className="text-sm text-muted-foreground">{machine.name}</p>
        </div>
        <Button variant="outline" size="icon" onClick={load} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          <span className="sr-only">Refresh</span>
        </Button>
      </div>

      {!report && loaded ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Belum ada data sensor untuk mesin ini.
          </CardContent>
        </Card>
      ) : report ? (
        <>
          <PredictionCard report={report} />

          {status && status.earlyWarning.length > 0 && (
            <div>
              <h2 className="mb-2 text-sm font-medium text-muted-foreground">
                AI Early Warning
              </h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {status.earlyWarning.map((item) => (
                  <EarlyWarningCard key={item.parameter} item={item} />
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  AI Diagnosis
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Primary Contributing Factor
                  </p>
                  <p className="font-medium">
                    {report.shap.features[0]?.featureName ?? "-"}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Probability
                  </p>
                  <p className="text-2xl font-bold tabular-nums">
                    {(report.prediction.failureProbability * 100).toFixed(0)}
                    /100
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <Sparkles className="size-4" />
                  AI Explanation
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                {report.recommendedAction && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground">
                      KNN Delta ({report.recommendedAction.feature})
                    </p>
                    <p className="tabular-nums">
                      {report.recommendedAction.currentValue} →{" "}
                      {report.recommendedAction.targetValue}
                    </p>
                  </div>
                )}
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Cause Analysis
                  </p>
                  <p>{report.causeAnalysisShort || "-"}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Suggestions for Improvement
                  </p>
                  <p>{report.suggestionGeneral || "-"}</p>
                </div>
              </CardContent>
            </Card>
          </div>

          {report.horizonPrediction && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="size-3.5" />
              Horizon model version {report.horizonPrediction.modelVersion} ·
              threshold {(report.horizonPrediction.threshold * 100).toFixed(1)}%
            </p>
          )}
        </>
      ) : null}
    </div>
  );
}

export default function MachineDiagnosisPage() {
  return (
    <RequireActiveMachine>
      {(machine) => <MachineDiagnosisContent machine={machine} />}
    </RequireActiveMachine>
  );
}
