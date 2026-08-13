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
          Estimasi Kerugian Downtime
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        <div className="flex justify-between">
          <span>Kerugian per jam</span>
          <span className="font-medium tabular-nums">
            {formatRupiah(data.costPerHourIdr)}
          </span>
        </div>
        <div className="flex justify-between">
          <span>Perbaikan sekarang (±{data.estimatedRepairHours} jam)</span>
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
            <span>Jika ditunda {p.delayHours} jam</span>
            <span className="font-medium tabular-nums">
              +{formatRupiah(p.additionalLossIdr)}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
