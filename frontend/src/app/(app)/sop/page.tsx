"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText, Pencil, RefreshCw, Trash2 } from "lucide-react";
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
import { SopFormDialog } from "@/components/sop-form-dialog";
import { RequireActiveMachine } from "@/components/require-active-machine";
import { useSops } from "@/hooks/use-sops";
import { listKnowledgeBaseDocumentsAction } from "@/app/actions/knowledgebase";
import { deleteSop } from "@/lib/sops";
import { cn } from "@/lib/utils";
import type { KnowledgeBaseDocument, Machine, Sop } from "@/lib/types";

function statusLabel(status: string): string {
  switch (status) {
    case "completed":
      return "Selesai";
    case "processing":
      return "Diproses";
    case "rejected_duplicate":
      return "Duplikat";
    case "failed":
      return "Gagal";
    default:
      return status;
  }
}

function statusBadgeClass(status: string): string {
  if (status === "completed") {
    return "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300";
  }
  if (status === "processing") {
    return "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300";
  }
  return "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
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

function KnowledgeBaseDocuments({ machine }: { machine: Machine }) {
  const [documents, setDocuments] = useState<KnowledgeBaseDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const docs = await listKnowledgeBaseDocumentsAction(machine.id);
      setDocuments(docs);
    } catch (err) {
      unstable_rethrow(err);
      toast.error(
        err instanceof Error ? err.message : "Gagal memuat dokumen manual.",
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

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium">Dokumen Manual Servis</h2>
          <p className="text-xs text-muted-foreground">
            Manual/troubleshooting guide {machine.name} yang dipakai sistem
            untuk analisis root-cause otomatis (RAG).
          </p>
        </div>
        <Button variant="outline" size="icon" onClick={load} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          <span className="sr-only">Refresh</span>
        </Button>
      </div>

      {documents.length === 0 && loaded ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          Belum ada dokumen manual untuk mesin ini.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {documents.map((d) => (
            <Card key={d.id} className="gap-2 py-3">
              <CardContent className="flex items-center justify-between gap-3 px-4">
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <FileText className="size-4 shrink-0 text-muted-foreground" />
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-sm font-medium">
                      {d.originalFilename ?? d.docName}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {d.chunkCount} bagian · {formatTimestamp(d.uploadedAt)}
                    </span>
                  </div>
                </div>
                <Badge className={cn("shrink-0 text-[10px]", statusBadgeClass(d.status))}>
                  {statusLabel(d.status)}
                </Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function SopSection() {
  const { sops, loading } = useSops();
  const [addOpen, setAddOpen] = useState(false);
  const [editSop, setEditSop] = useState<Sop | undefined>(undefined);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium">SOP Terstruktur</h2>
          <p className="text-xs text-muted-foreground">
            Dipakai chatbot untuk merekomendasikan penanganan (tidak terikat
            mesin tertentu).
          </p>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Tambah SOP
        </Button>
      </div>

      {sops.length === 0 && !loading ? (
        <div className="flex flex-col items-center gap-4 py-10">
          <FileText className="text-muted-foreground size-10" />
          <p className="text-muted-foreground text-sm">Belum ada SOP tersimpan.</p>
          <Button onClick={() => setAddOpen(true)}>Tambah SOP Pertama</Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {sops.map((s) => (
            <Card key={s.id} className="py-0">
              <CardContent className="flex flex-col gap-3 p-4">
                <div className="flex items-start gap-3">
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className="font-medium">{s.title}</span>
                    {s.body && (
                      <span className="text-muted-foreground line-clamp-2 text-xs">
                        {s.body}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setEditSop(s)}
                    >
                      <Pencil className="size-4" />
                      <span className="sr-only">Edit SOP</span>
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger
                        render={<Button variant="ghost" size="icon" />}
                      >
                        <Trash2 className="size-4" />
                        <span className="sr-only">Hapus SOP</span>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Hapus SOP?</AlertDialogTitle>
                          <AlertDialogDescription>
                            SOP &quot;{s.title}&quot; akan dihapus dari
                            knowledge base. Chatbot tidak lagi memakainya
                            untuk rekomendasi.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Batal</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={async () => {
                              try {
                                await deleteSop(s.id);
                                toast.success("SOP dihapus.");
                              } catch (err) {
                                unstable_rethrow(err);
                                toast.error(
                                  err instanceof Error
                                    ? err.message
                                    : "Gagal menghapus SOP.",
                                );
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
                  <span className="text-muted-foreground text-sm">
                    {s.steps.length} langkah
                  </span>
                  {s.reference && (
                    <span className="text-muted-foreground truncate text-xs">
                      · {s.reference}
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <SopFormDialog open={addOpen} onOpenChange={setAddOpen} onSaved={() => {}} />
      <SopFormDialog
        open={editSop !== undefined}
        onOpenChange={(o) => {
          if (!o) setEditSop(undefined);
        }}
        sop={editSop}
        onSaved={() => {}}
      />
    </div>
  );
}

function KnowledgeBaseContent({ machine }: { machine: Machine }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 overflow-y-auto p-6">
      <div>
        <h1 className="text-xl font-semibold">Knowledge Base</h1>
        <p className="text-muted-foreground text-sm">
          Dokumen manual servis dan SOP yang dipakai sistem untuk analisis dan
          rekomendasi penanganan.
        </p>
      </div>

      <KnowledgeBaseDocuments machine={machine} />
      <SopSection />
    </div>
  );
}

export default function SopPage() {
  return (
    <RequireActiveMachine>
      {(machine) => <KnowledgeBaseContent machine={machine} />}
    </RequireActiveMachine>
  );
}
