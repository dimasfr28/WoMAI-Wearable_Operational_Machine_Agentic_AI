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
      return "Completed";
    case "processing":
      return "Processing";
    case "rejected_duplicate":
      return "Duplicate";
    case "failed":
      return "Failed";
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
  return new Date(iso).toLocaleString("en-US", {
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
        err instanceof Error ? err.message : "Failed to load manual documents.",
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
          <h2 className="text-sm font-medium">Service Manual Documents</h2>
          <p className="text-xs text-muted-foreground">
            Manual/troubleshooting guide for {machine.name}, used by the
            system for automatic root-cause analysis (RAG).
          </p>
        </div>
        <Button variant="outline" size="icon" onClick={load} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          <span className="sr-only">Refresh</span>
        </Button>
      </div>

      {documents.length === 0 && loaded ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No manual documents yet for this machine.
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
                      {d.chunkCount} sections · {formatTimestamp(d.uploadedAt)}
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
          <h2 className="text-sm font-medium">Structured SOPs</h2>
          <p className="text-xs text-muted-foreground">
            Used by the chatbot to recommend handling steps (not tied to a
            specific machine).
          </p>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Add SOP
        </Button>
      </div>

      {sops.length === 0 && !loading ? (
        <div className="flex flex-col items-center gap-4 py-10">
          <FileText className="text-muted-foreground size-10" />
          <p className="text-muted-foreground text-sm">No SOPs saved yet.</p>
          <Button onClick={() => setAddOpen(true)}>Add First SOP</Button>
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
                        <span className="sr-only">Delete SOP</span>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete SOP?</AlertDialogTitle>
                          <AlertDialogDescription>
                            SOP &quot;{s.title}&quot; will be deleted from
                            the knowledge base. The chatbot will no longer
                            use it for recommendations.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={async () => {
                              try {
                                await deleteSop(s.id);
                                toast.success("SOP deleted.");
                              } catch (err) {
                                unstable_rethrow(err);
                                toast.error(
                                  err instanceof Error
                                    ? err.message
                                    : "Failed to delete SOP.",
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
                  <span className="text-muted-foreground text-sm">
                    {s.steps.length} steps
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
          Service manual documents and SOPs used by the system for analysis
          and handling recommendations.
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
