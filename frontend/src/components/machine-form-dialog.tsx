"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { saveMachine } from "@/lib/machines";
import type { Machine } from "@/lib/types";

interface MachineFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  machine?: Machine;
  onSaved: (m: Machine) => void;
}

export function MachineFormDialog({
  open,
  onOpenChange,
  machine,
  onSaved,
}: MachineFormDialogProps) {
  const [name, setName] = useState("");
  const [type, setType] = useState<Machine["type"]>("M");
  const [line, setLine] = useState("");
  const [notes, setNotes] = useState("");

  // Reset form when dialog opens; prefill from machine prop in edit mode
  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setName(machine?.name ?? "");
    setType(machine?.type ?? "M");
    setLine(machine?.line ?? "");
    setNotes(machine?.notes ?? "");
  }, [open, machine]);

  const [saving, setSaving] = useState(false);
  const canSave = name.trim().length > 0 && !saving;

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    const trimmedLine = line.trim();
    const trimmedNotes = notes.trim();
    try {
      const saved = await saveMachine({
        id: machine?.id,
        name: name.trim(),
        type,
        line: trimmedLine || undefined,
        notes: trimmedNotes || undefined,
      });
      onSaved(saved);
      onOpenChange(false);
    } catch {
      toast.error("Gagal menyimpan mesin.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {machine ? "Edit Mesin" : "Tambah Mesin"}
          </DialogTitle>
          <DialogDescription>
            {machine
              ? "Perbarui informasi mesin."
              : "Tambahkan mesin baru ke daftar."}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="mesin-nama">
              Nama mesin <span className="text-destructive">*</span>
            </Label>
            <Input
              id="mesin-nama"
              placeholder="mis. Motor Line 3"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="mesin-tipe">Tipe mesin</Label>
            <Select
              value={type}
              onValueChange={(v) => {
                if (v) setType(v as Machine["type"]);
              }}
            >
              <SelectTrigger id="mesin-tipe" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="L">L (Low)</SelectItem>
                <SelectItem value="M">M (Medium)</SelectItem>
                <SelectItem value="H">H (High)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="mesin-line">Line (opsional)</Label>
            <Input
              id="mesin-line"
              placeholder="mis. Line 3"
              value={line}
              onChange={(e) => setLine(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="mesin-catatan">Catatan (opsional)</Label>
            <Textarea
              id="mesin-catatan"
              placeholder="mis. Motor pompa air utama"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="resize-none"
            />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" onClick={handleSave} disabled={!canSave}>
            Simpan Mesin
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
