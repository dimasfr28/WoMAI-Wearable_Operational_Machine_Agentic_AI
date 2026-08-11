"use client";

import { useState } from "react";
import { FileText, Pencil, Trash2 } from "lucide-react";
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
import { useSops } from "@/hooks/use-sops";
import { deleteSop } from "@/lib/sops";
import { SOP_MODE_LABEL, type Sop } from "@/lib/types";

export default function SopPage() {
  const { sops, loading } = useSops();
  const [addOpen, setAddOpen] = useState(false);
  const [editSop, setEditSop] = useState<Sop | undefined>(undefined);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <h1 className="text-xl font-semibold">SOP File</h1>
          <p className="text-muted-foreground text-sm">
            Knowledge base tindakan yang dipakai chatbot untuk merekomendasikan
            penanganan.
          </p>
          <p className="text-xs text-muted-foreground">
            Mode demo: perubahan SOP di halaman ini belum tersimpan permanen.
          </p>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Tambah SOP
        </Button>
      </div>

      {sops.length === 0 && !loading ? (
        <div className="flex flex-col items-center gap-4 py-16">
          <FileText className="text-muted-foreground size-12" />
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
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">{s.mode}</Badge>
                      <span className="font-medium">{s.title}</span>
                    </div>
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
                            SOP &quot;{s.title}&quot; ({SOP_MODE_LABEL[s.mode]})
                            akan dihapus dari knowledge base. Chatbot tidak lagi
                            memakainya untuk rekomendasi.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Batal</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={async () => {
                              try {
                                await deleteSop(s.id);
                                toast.success("SOP dihapus.");
                              } catch {
                                toast.error("Gagal menghapus SOP.");
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
