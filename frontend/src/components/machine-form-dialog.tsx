"use client";

import { useEffect, useState } from "react";
import { unstable_rethrow } from "next/navigation";
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
      unstable_rethrow(err);
      toast.error(err instanceof Error ? err.message : "Failed to save machine.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {machine ? "Edit Machine" : "Add Machine"}
          </DialogTitle>
          <DialogDescription>
            {machine
              ? "Update the machine's information."
              : "Add a new machine to the list."}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="mesin-nama">
              Machine name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="mesin-nama"
              placeholder="e.g. CNC Mill 01"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="mesin-tipe">Machine type (optional)</Label>
            <Input
              id="mesin-tipe"
              placeholder="e.g. Haas"
              value={machineType}
              onChange={(e) => setMachineType(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" onClick={handleSave} disabled={!canSave}>
            Save Machine
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
