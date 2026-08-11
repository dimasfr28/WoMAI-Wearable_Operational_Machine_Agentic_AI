"use client";

import Link from "next/link";
import { useState } from "react";
import { Factory, MessageSquareText, Pencil, Trash2 } from "lucide-react";
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
import { useSessions } from "@/hooks/use-sessions";
import { deleteMachine } from "@/lib/machines";
import type { Machine } from "@/lib/types";
import { RISK_BADGE } from "@/lib/risk";
import { cn } from "@/lib/utils";

export default function MesinPage() {
  const { machines } = useMachines();
  const { sessions } = useSessions();
  const [addOpen, setAddOpen] = useState(false);
  const [editMachine, setEditMachine] = useState<Machine | undefined>(
    undefined,
  );

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">Mesin</h1>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Tambah Mesin
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Mode demo: perubahan data mesin di halaman ini belum tersimpan
        permanen.
      </p>

      {machines.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-16">
          <Factory className="size-12 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Belum ada mesin terdaftar.
          </p>
          <Button onClick={() => setAddOpen(true)}>
            Tambah Mesin Pertama
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
              <Card key={m.id} className="py-0">
                <CardContent className="flex flex-col gap-3 p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <span className="font-medium">{m.name}</span>
                      {(m.line ?? m.notes) && (
                        <span className="text-xs text-muted-foreground">
                          {[m.line, m.notes].filter(Boolean).join(" · ")}
                        </span>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Badge variant="secondary">Tipe {m.type}</Badge>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setEditMachine(m)}
                      >
                        <Pencil className="size-4" />
                        <span className="sr-only">Edit mesin</span>
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger
                          render={<Button variant="ghost" size="icon" />}
                        >
                          <Trash2 className="size-4" />
                          <span className="sr-only">Hapus mesin</span>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Hapus mesin?</AlertDialogTitle>
                            <AlertDialogDescription>
                              Mesin &quot;{m.name}&quot; akan dihapus. Sesi
                              lama yang sudah terekam tetap tersimpan dengan
                              nama mesin saat itu.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Batal</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={async () => {
                                try {
                                  await deleteMachine(m.id);
                                  toast.success("Mesin dihapus.");
                                } catch {
                                  toast.error("Gagal menghapus mesin.");
                                }
                              }}
                            >
                              Hapus
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-muted-foreground">
                      {sessionCount} sesi
                    </span>
                    {lastPrediction ? (
                      <Badge
                        className={cn(RISK_BADGE[lastPrediction.riskLevel])}
                      >
                        {lastPrediction.failureType === "NONE"
                          ? "Normal"
                          : `${lastPrediction.failureType} · risiko ${lastPrediction.riskLevel}`}
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Belum ada prediksi</Badge>
                    )}
                    {sessionCount > 0 && (
                      <Link
                        href={`/riwayat?mesin=${m.id}`}
                        className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                      >
                        <MessageSquareText className="size-3.5" />
                        Lihat sesi
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
        onSaved={() => {}}
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
