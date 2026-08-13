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
  const [machineType, setMachineType] = useState("");

  // Reset form when dialog opens; prefill from machine prop in edit mode
  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setName(machine?.name ?? "");
    setMachineType(machine?.machineType ?? "");
  }, [open, machine]);

  const [saving, setSaving] = useState(false);
  const canSave = name.trim().length > 0 && !saving;

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    const trimmedType = machineType.trim();
    try {
      const saved = await saveMachine({
        id: machine?.id,
        name: name.trim(),
        machineType: trimmedType || undefined,
      });
      onSaved(saved);
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gagal menyimpan mesin.");
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
              placeholder="mis. CNC Mill 01"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="mesin-tipe">Tipe mesin (opsional)</Label>
            <Input
              id="mesin-tipe"
              placeholder="mis. Haas"
              value={machineType}
              onChange={(e) => setMachineType(e.target.value)}
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
