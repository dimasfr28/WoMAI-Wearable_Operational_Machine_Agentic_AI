import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ShapResult } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ShapCard({ data }: { data: ShapResult }) {
  const sorted = [...data.contributions].sort(
    (a, b) => Math.abs(b.value) - Math.abs(a.value),
  );
  const max = Math.max(...sorted.map((c) => Math.abs(c.value)), 0.01);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Prediction Drivers (SHAP)
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {sorted.map((c) => (
          <div key={c.feature} className="flex items-center gap-3 text-sm">
            <span className="w-28 shrink-0 truncate sm:w-48">{c.feature}</span>
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full",
                  c.value > 0
                    ? "bg-red-400"
                    : c.value < 0
                      ? "bg-emerald-400"
                      : "bg-muted-foreground/30",
                )}
                style={{ width: `${(Math.abs(c.value) / max) * 100}%` }}
              />
            </div>
            <span className="w-14 shrink-0 text-right tabular-nums text-muted-foreground">
              {c.value > 0 ? "+" : c.value < 0 ? "−" : ""}
              {Math.abs(c.value).toFixed(2)}
            </span>
          </div>
        ))}
        <p className="pt-1 text-xs text-muted-foreground">
          Red increases failure risk; green decreases it.
        </p>
      </CardContent>
    </Card>
  );
}
