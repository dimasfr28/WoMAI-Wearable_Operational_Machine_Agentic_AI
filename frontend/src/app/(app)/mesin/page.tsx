"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Factory, MessageSquareText, Pencil, Trash2 } from "lucide-react";
import { unstable_rethrow } from "next/navigation";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MachineFormDialog } from "@/components/machine-form-dialog";
import { useMachines } from "@/hooks/use-machines";
import { useActiveMachine } from "@/hooks/use-active-machine";
import { useSessions } from "@/hooks/use-sessions";
import { deleteMachine } from "@/lib/machines";
import type { Machine } from "@/lib/types";
import { RISK_BADGE, RISK_LABEL } from "@/lib/risk";
import { cn } from "@/lib/utils";

export default function MesinPage() {
  const { machines } = useMachines();
  const { setActiveMachine } = useActiveMachine();
  const { sessions } = useSessions();
  const router = useRouter();
  const [addOpen, setAddOpen] = useState(false);
  const [editMachine, setEditMachine] = useState<Machine | undefined>(
    undefined,
  );

  function selectMachine(m: Machine) {
    setActiveMachine(m);
    router.push("/chat");
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Select Machine</h1>
          <p className="text-sm text-muted-foreground">
            Select a machine to start a consultation, or manage the
            machine list below.
          </p>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Add Machine
        </Button>
      </div>

      {machines.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-16">
          <Factory className="size-12 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            No machines registered yet.
          </p>
          <Button onClick={() => setAddOpen(true)}>
            Add First Machine
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {machines.map((m) => {
            const machineSessions = sessions.filter(
              (s) => s.machineId === m.id,
            );
            const sessionCount = machineSessions.length;
            const lastPrediction = machineSessions.find(
              (s) => s.lastPrediction,
            )?.lastPrediction;

            return (
              <Card
                key={m.id}
                className="cursor-pointer py-0 transition-colors hover:border-primary/50"
                onClick={() => selectMachine(m)}
              >
                <CardContent className="flex flex-col gap-3 p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <span className="font-medium">{m.name}</span>
                      {m.machineType && (
                        <span className="text-xs text-muted-foreground">
                          {m.machineType}
                        </span>
                      )}
                    </div>
                    <div
                      className="flex shrink-0 items-center gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Badge variant="secondary">{m.status}</Badge>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setEditMachine(m)}
                      >
                        <Pencil className="size-4" />
                        <span className="sr-only">Edit machine</span>
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger
                          render={<Button variant="ghost" size="icon" />}
                        >
                          <Trash2 className="size-4" />
                          <span className="sr-only">Delete machine</span>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Delete machine?</AlertDialogTitle>
                            <AlertDialogDescription>
                              Machine &quot;{m.name}&quot; will be deleted.
                              Previously recorded sessions stay saved under
                              the machine name they had at the time.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={async () => {
                                try {
                                  await deleteMachine(m.id);
                                  toast.success("Machine deleted.");
                                } catch (err) {
                                  unstable_rethrow(err);
                                  toast.error(
                                    err instanceof Error
                                      ? err.message
                                      : "Failed to delete machine.",
                                  );
                                }
                              }}
                            >
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-muted-foreground">
                      {m.documentCount} documents · {m.runCount} runs ·{" "}
                      {sessionCount} sessions
                    </span>
                    {lastPrediction ? (
                      <Badge
                        className={cn(RISK_BADGE[lastPrediction.riskLevel])}
                      >
                        {lastPrediction.label
                          ? `Potential failure · ${RISK_LABEL[lastPrediction.riskLevel]} risk`
                          : "Normal"}
                      </Badge>
                    ) : (
                      <Badge variant="secondary">No prediction yet</Badge>
                    )}
                    {sessionCount > 0 && (
                      <Link
                        href={`/riwayat?mesin=${m.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                      >
                        <MessageSquareText className="size-3.5" />
                        View sessions
                      </Link>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <MachineFormDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onSaved={(m) => selectMachine(m)}
      />
      <MachineFormDialog
        open={editMachine !== undefined}
        onOpenChange={(o) => {
          if (!o) setEditMachine(undefined);
        }}
        machine={editMachine}
        onSaved={() => {}}
      />
    </div>
  );
}
