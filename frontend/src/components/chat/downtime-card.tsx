import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { formatRupiah } from "@/lib/format";
import type { DowntimeEstimate } from "@/lib/types";

export function DowntimeCard({ data }: { data: DowntimeEstimate }) {
  const repairLoss = data.costPerHourIdr * data.estimatedRepairHours;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Downtime Loss Estimate
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        <div className="flex justify-between">
          <span>Loss per hour</span>
          <span className="font-medium tabular-nums">
            {formatRupiah(data.costPerHourIdr)}
          </span>
        </div>
        <div className="flex justify-between">
          <span>Repair now (±{data.estimatedRepairHours} hrs)</span>
          <span className="font-medium tabular-nums">
            {formatRupiah(repairLoss)}
          </span>
        </div>
        <Separator />
        {data.projections.map((p) => (
          <div
            key={p.delayHours}
            className="flex justify-between text-red-600"
          >
            <span>If delayed {p.delayHours} hrs</span>
            <span className="font-medium tabular-nums">
              +{formatRupiah(p.additionalLossIdr)}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
