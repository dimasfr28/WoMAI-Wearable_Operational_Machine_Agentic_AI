"use client";

import { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import { unstable_rethrow } from "next/navigation";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  CircleAlert,
  Clock,
  Gauge,
  RefreshCw,
  Sparkles,
  Thermometer,
  Wifi,
  WifiOff,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { getReportAction } from "@/app/actions/report";
import { getMachineStatusAction } from "@/app/actions/machine-status";
import { RequireActiveMachine } from "@/components/require-active-machine";
import { cn } from "@/lib/utils";
import type { EarlyWarningItem, Machine, MachineStatus, ReportData } from "@/lib/types";

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Freshness of the last reading received from the machine's IoT (ESP32)
// client — "live" within ~2 normal submit intervals (~60s each), "stale"
// once it's been a while but still recent, "offline" past 10 minutes with
// no new data at all.
type DataFreshness = "live" | "stale" | "offline";

function dataFreshness(lastReadingAt: string | null, now: Date): DataFreshness {
  if (!lastReadingAt) return "offline";
  const ageMinutes = (now.getTime() - new Date(lastReadingAt).getTime()) / 60_000;
  if (ageMinutes <= 2) return "live";
  if (ageMinutes <= 10) return "stale";
  return "offline";
}

function formatRelativeTime(iso: string, now: Date): string {
  const ageSeconds = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
  if (ageSeconds < 60) return "just now";
  const ageMinutes = Math.round(ageSeconds / 60);
  if (ageMinutes < 60) return `${ageMinutes} min ago`;
  const ageHours = Math.round(ageMinutes / 60);
  if (ageHours < 24) return `${ageHours} hr ago`;
  return `${Math.round(ageHours / 24)} d ago`;
}

const FRESHNESS_STYLE: Record<DataFreshness, string> = {
  live: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400",
  stale: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-400",
  offline: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400",
};

function DataFreshnessBadge({
  lastReadingAt,
  now,
}: {
  lastReadingAt: string | null;
  now: Date;
}) {
  const freshness = dataFreshness(lastReadingAt, now);
  const Icon = freshness === "offline" ? WifiOff : Wifi;
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        FRESHNESS_STYLE[freshness],
      )}
      title={lastReadingAt ? `Last ESP32 reading: ${formatTimestamp(lastReadingAt)}` : "No sensor data received yet"}
    >
      <Icon className="size-3.5" />
      {lastReadingAt ? (
        <span>
          IoT data {formatRelativeTime(lastReadingAt, now)}
        </span>
      ) : (
        <span>No IoT data yet</span>
      )}
    </div>
  );
}

const EARLY_WARNING_ICON: Record<string, typeof Clock> = {
  tool_wear_min: Clock,
  rotational_speed_rpm: Gauge,
  air_temperature_k: Thermometer,
  process_temperature_k: Thermometer,
};

function EarlyWarningCard({ item }: { item: EarlyWarningItem }) {
  const Icon = EARLY_WARNING_ICON[item.parameter] ?? Gauge;
  return (
    <Card
      className={cn(
        "border py-4",
        item.isAnomaly
          ? "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30"
          : "border-emerald-200 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/30",
      )}
    >
      <CardContent className="flex items-center gap-3 px-4">
        <div
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-full",
            item.isAnomaly
              ? "bg-red-100 text-red-600 dark:bg-red-900/50 dark:text-red-400"
              : "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-400",
          )}
        >
          <Icon className="size-5" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-muted-foreground">
            {item.parameterLabel}
          </p>
          <p
            className={cn(
              "text-xl font-bold tabular-nums",
              item.isAnomaly
                ? "text-red-700 dark:text-red-400"
                : "text-emerald-700 dark:text-emerald-400",
            )}
          >
            {item.currentValue}{" "}
            <span className="text-xs font-normal text-muted-foreground">
              {item.unit}
            </span>
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function PredictionCard({ report }: { report: ReportData }) {
  const failed = report.prediction.predictedLabel;
  return (
    <Card
      className={cn(
        "border",
        failed
          ? "border-red-200 bg-gradient-to-r from-red-50 to-red-50/60 dark:border-red-900 dark:from-red-950/40 dark:to-red-950/10"
          : "border-emerald-200 bg-gradient-to-r from-emerald-50 to-emerald-50/60 dark:border-emerald-900 dark:from-emerald-950/40 dark:to-emerald-950/10",
      )}
    >
      <CardContent className="flex flex-col gap-4 py-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <div
            className={cn(
              "flex size-14 shrink-0 items-center justify-center rounded-full",
              failed
                ? "bg-red-100 dark:bg-red-900/50"
                : "bg-emerald-100 dark:bg-emerald-900/50",
            )}
          >
            {failed ? (
              <AlertTriangle className="size-7 text-red-600 dark:text-red-400" />
            ) : (
              <CheckCircle2 className="size-7 text-emerald-600 dark:text-emerald-400" />
            )}
          </div>
          <div>
            <p
              className={cn(
                "text-xl font-bold",
                failed
                  ? "text-red-700 dark:text-red-400"
                  : "text-emerald-700 dark:text-emerald-400",
              )}
            >
              {failed ? "Failure Predicted" : "Healthy"}
            </p>
            <p className="text-sm text-muted-foreground">
              Machine health prediction based on the latest data recorded at{" "}
              {formatTimestamp(report.sensor.readingTimestamp)}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-8 self-end sm:self-auto">
          <div className="flex flex-col items-end gap-1">
            <span className="text-xs text-muted-foreground">Failure Risk</span>
            <span
              className={cn(
                "text-3xl font-bold tabular-nums",
                failed
                  ? "text-red-700 dark:text-red-400"
                  : "text-emerald-700 dark:text-emerald-400",
              )}
            >
              {(report.prediction.failureProbability * 100).toFixed(1)}%
            </span>
          </div>
          {report.horizonPrediction && (
            <>
              <div className="h-12 w-px bg-border" />
              <div className="flex flex-col items-end gap-1">
                <span className="text-xs text-muted-foreground">
                  Failure in +{report.horizonPrediction.horizonMinutes} Minute
                </span>
                <span
                  className={cn(
                    "text-3xl font-bold tabular-nums",
                    failed
                      ? "text-red-700 dark:text-red-400"
                      : "text-emerald-700 dark:text-emerald-400",
                  )}
                >
                  {(report.horizonPrediction.failureProbability * 100).toFixed(1)}
                  %
                </span>
              </div>
            </>
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
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    // Ticks the freshness badge's "X min ago" without needing a refetch.
    const interval = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(interval);
  }, []);

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
      toast.error(err instanceof Error ? err.message : "Failed to load diagnosis.");
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
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="relative size-12 shrink-0 overflow-hidden rounded-xl">
            <Image
              src="/images/womai_logo.png"
              alt="WO.M.AI Logo"
              fill
              sizes="48px"
              className="object-cover"
            />
          </div>
          <div>
            <h1 className="text-xl font-bold">Machine Diagnosis</h1>
            <p className="text-sm text-muted-foreground">{machine.name}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {status && <DataFreshnessBadge lastReadingAt={status.lastReadingAt} now={now} />}
          <Button variant="outline" size="icon" onClick={load} disabled={loading}>
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            <span className="sr-only">Refresh</span>
          </Button>
        </div>
      </div>

      {!report && loaded ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No sensor data yet for this machine.
          </CardContent>
        </Card>
      ) : report ? (
        <>
          <PredictionCard report={report} />

          {status && status.earlyWarning.length > 0 && (
            <div>
              <h2 className="mb-2 text-lg font-bold">AI Early Warning</h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {status.earlyWarning.map((item) => (
                  <EarlyWarningCard key={item.parameter} item={item} />
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card className="relative overflow-hidden">
              <Brain
                className="pointer-events-none absolute -right-6 -bottom-6 size-44 text-blue-100 dark:text-blue-950/60"
                strokeWidth={1}
              />
              <CardContent className="relative flex flex-col gap-4 text-sm">
                <p className="flex items-center gap-2 text-base font-bold">
                  <Brain className="size-5 text-blue-600 dark:text-blue-400" />
                  AI Diagnosis
                </p>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">
                    Primary Contributing Factor
                  </p>
                  <span className="inline-block w-fit rounded-md bg-blue-50 px-2.5 py-1 font-mono text-sm font-medium text-blue-700 dark:bg-blue-950/50 dark:text-blue-400">
                    {report.shap.features[0]?.featureName ?? "-"}
                  </span>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">
                    Health Score
                  </p>
                  <p className="text-5xl font-bold tabular-nums">
                    {Math.round(report.prediction.healthScore)}
                    <span className="text-lg font-normal text-muted-foreground">
                      /100
                    </span>
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="flex flex-col gap-3 text-sm">
                <p className="flex items-center gap-2 text-base font-bold">
                  <Sparkles className="size-5 text-blue-600 dark:text-blue-400" />
                  AI Explanation
                </p>
                {report.recommendedAction && (
                  <div className="rounded-lg bg-blue-50 p-3 dark:bg-blue-950/40">
                    <p className="mb-1 text-xs font-medium text-muted-foreground">
                      KNN Delta ({report.recommendedAction.feature})
                    </p>
                    <p className="flex items-center gap-2 font-semibold tabular-nums text-blue-700 dark:text-blue-400">
                      {report.recommendedAction.currentValue}
                      <span aria-hidden="true">→</span>
                      {report.recommendedAction.targetValue}
                    </p>
                  </div>
                )}
                <div className="flex gap-2 rounded-lg bg-orange-50 p-3 dark:bg-orange-950/30">
                  <CircleAlert className="mt-0.5 size-4 shrink-0 text-orange-600 dark:text-orange-400" />
                  <div>
                    <p className="font-semibold text-orange-700 dark:text-orange-400">
                      Cause Analysis
                    </p>
                    <p className="text-muted-foreground">
                      {report.causeAnalysisShort || "-"}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2 rounded-lg bg-blue-50 p-3 dark:bg-blue-950/40">
                  <Wrench className="mt-0.5 size-4 shrink-0 text-blue-600 dark:text-blue-400" />
                  <div>
                    <p className="font-semibold text-blue-700 dark:text-blue-400">
                      Suggestions for Improvement
                    </p>
                    <p className="text-muted-foreground">
                      {report.suggestionGeneral || "-"}
                    </p>
                  </div>
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
