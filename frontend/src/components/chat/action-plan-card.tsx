"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import type { SopPlan } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ActionPlanCardProps {
  plan: SopPlan;
  checkedSteps: Record<string, boolean>;
  onToggleStep: (stepId: string) => void;
}

export function ActionPlanCard({
  plan,
  checkedSteps,
  onToggleStep,
}: ActionPlanCardProps) {
  const done = plan.steps.filter((s) => checkedSteps[s.id]).length;
  const totalMinutes = plan.steps.reduce(
    (sum, s) => sum + s.estimatedMinutes,
    0,
  );

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Rencana Tindakan · {plan.title}
          </CardTitle>
          <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
            {done}/{plan.steps.length} langkah · ±{totalMinutes} menit
          </span>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        {plan.steps.map((step) => {
          const checked = Boolean(checkedSteps[step.id]);
          return (
            <label
              key={step.id}
              className="flex cursor-pointer items-start gap-3 rounded-md px-2 py-2 hover:bg-accent"
            >
              <Checkbox
                checked={checked}
                onCheckedChange={() => onToggleStep(step.id)}
                className="mt-0.5"
              />
              <span
                className={cn(
                  "flex-1 text-sm",
                  checked && "text-muted-foreground line-through",
                )}
              >
                {step.text}
              </span>
              <span className="flex shrink-0 items-center gap-2">
                <Badge
                  variant={
                    step.priority === "segera" ? "destructive" : "secondary"
                  }
                >
                  {step.priority === "segera" ? "Segera" : "Terjadwal"}
                </Badge>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {step.estimatedMinutes}m
                </span>
              </span>
            </label>
          );
        })}
      </CardContent>
    </Card>
  );
}
