"use client";

import { useCallback, useEffect, useState } from "react";
import { unstable_rethrow } from "next/navigation";
import { FileText, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  getLatestMachineReportAction,
  listMachineReportsAction,
} from "@/app/actions/machine-report";
import { RequireActiveMachine } from "@/components/require-active-machine";
import { cn } from "@/lib/utils";
import type { Machine, MachineReportItem } from "@/lib/types";

function statusBadgeClass(status: string): string {
  if (status === "Failure") {
    return "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
  }
  if (status === "Warning") {
    return "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300";
  }
  return "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300";
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString("id-ID", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function MachineReportContent({ machine }: { machine: Machine }) {
  const [reports, setReports] = useState<MachineReportItem[]>([]);
  const [selected, setSelected] = useState<MachineReportItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [latest, history] = await Promise.all([
        getLatestMachineReportAction(machine.id),
        listMachineReportsAction(machine.id),
      ]);
      setReports(history);
      setSelected(latest ?? history[0] ?? null);
    } catch (err) {
      unstable_rethrow(err);
      toast.error(
        err instanceof Error ? err.message : "Gagal memuat Machine Report.",
      );
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [machine.id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount/on-machine-change
    load();
  }, [load]);

  const pdfSrc = selected
    ? `/api/machine-report/${encodeURIComponent(selected.id)}/pdf`
    : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between gap-4 border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">Machine Report</h1>
          <p className="text-sm text-muted-foreground">{machine.name}</p>
        </div>
        <Button variant="outline" size="icon" onClick={load} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          <span className="sr-only">Refresh</span>
        </Button>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 flex-1 overflow-hidden bg-muted/30">
          {pdfSrc ? (
            <iframe
              key={pdfSrc}
              src={pdfSrc}
              title="Machine Report PDF"
              className="h-full w-full border-0"
            />
          ) : loaded ? (
            <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
              Belum ada Machine Report untuk mesin ini. Laporan akan dibuat
              otomatis setiap kali data sensor baru masuk.
            </div>
          ) : null}
        </div>

        <div className="w-72 shrink-0 overflow-y-auto border-l p-3">
          <p className="mb-2 px-1 text-xs font-medium text-muted-foreground">
            Riwayat Laporan
          </p>
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <Card
                key={r.id}
                className={cn(
                  "cursor-pointer gap-2 py-3 transition-colors hover:border-primary/50",
                  selected?.id === r.id && "border-primary",
                )}
                onClick={() => setSelected(r)}
              >
                <CardContent className="flex flex-col gap-1.5 px-3">
                  <div className="flex items-center gap-1.5 text-xs font-medium">
                    <FileText className="size-3.5 shrink-0" />
                    <span className="truncate">{r.reportNumber}</span>
                  </div>
                  <span className="text-[11px] text-muted-foreground">
                    {formatTimestamp(r.createdAt)}
                  </span>
                  <Badge
                    className={cn(
                      "w-fit text-[10px]",
                      statusBadgeClass(r.operatingStatus),
                    )}
                  >
                    {r.operatingStatus}
                  </Badge>
                </CardContent>
              </Card>
            ))}
            {reports.length === 0 && loaded && (
              <p className="px-1 text-xs text-muted-foreground">
                Belum ada laporan.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MachineReportPage() {
  return (
    <RequireActiveMachine>
      {(machine) => <MachineReportContent machine={machine} />}
    </RequireActiveMachine>
  );
}
