import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PredictionResult } from "@/lib/types";
import { RISK_BADGE, RISK_LABEL } from "@/lib/risk";
import { cn } from "@/lib/utils";

const RISK_RING: Record<PredictionResult["riskLevel"], string> = {
  tinggi: "stroke-red-500",
  sedang: "stroke-amber-500",
  rendah: "stroke-emerald-500",
};

export function PredictionCard({ data }: { data: PredictionResult }) {
  const pct = Math.round(data.probability * 100);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Failure Prediction
        </CardTitle>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <svg viewBox="0 0 36 36" className="size-20 shrink-0 -rotate-90">
            <circle
              cx="18"
              cy="18"
              r="15.915"
              fill="none"
              strokeWidth="3.5"
              className="stroke-muted"
            />
            <circle
              cx="18"
              cy="18"
              r="15.915"
              fill="none"
              strokeWidth="3.5"
              strokeLinecap="round"
              strokeDasharray={`${pct} ${100 - pct}`}
              className={cn(RISK_RING[data.riskLevel])}
            />
          </svg>
          <div className="flex flex-col gap-1">
            <div className="text-3xl font-bold tabular-nums">{pct}%</div>
            <div className="text-sm font-medium">
              {data.label ? "At risk of failure" : "Normal"}
            </div>
            <Badge className={cn("w-fit", RISK_BADGE[data.riskLevel])}>
              {RISK_LABEL[data.riskLevel]} Risk
            </Badge>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1 self-start">
          <span className="text-xs text-muted-foreground">Health Score</span>
          <p className="text-3xl font-bold tabular-nums">
            {Math.round(data.healthScore)}
            <span className="text-sm font-normal text-muted-foreground">
              /100
            </span>
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
