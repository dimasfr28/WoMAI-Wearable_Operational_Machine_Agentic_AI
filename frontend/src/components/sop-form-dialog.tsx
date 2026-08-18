"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { saveSop } from "@/lib/sops";
import type { Sop, SopStep } from "@/lib/types";

interface SopFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sop?: Sop;
  onSaved: (s: Sop) => void;
}

function emptyStep(): SopStep {
  return {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `step-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    text: "",
    priority: "segera",
    estimatedMinutes: 15,
  };
}

export function SopFormDialog({
  open,
  onOpenChange,
  sop,
  onSaved,
}: SopFormDialogProps) {
  const [title, setTitle] = useState("");
  const [symptoms, setSymptoms] = useState("");
  const [body, setBody] = useState("");
  const [reference, setReference] = useState("");
  const [steps, setSteps] = useState<SopStep[]>([]);

  // Reset saat dibuka; prefill dari prop sop di mode edit.
  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTitle(sop?.title ?? "");
    setSymptoms(sop?.symptoms ?? "");
    setBody(sop?.body ?? "");
    setReference(sop?.reference ?? "");
    setSteps(sop?.steps.length ? sop.steps.map((s) => ({ ...s })) : [emptyStep()]);
  }, [open, sop]);

  const [saving, setSaving] = useState(false);
  const canSave = title.trim().length > 0 && body.trim().length > 0 && !saving;

  function updateStep(id: string, patch: Partial<SopStep>) {
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    const cleanSteps = steps
      .filter((s) => s.text.trim().length > 0)
      .map((s) => ({
        ...s,
        text: s.text.trim(),
        estimatedMinutes: Math.max(0, Math.round(s.estimatedMinutes) || 0),
      }));
    try {
      const saved = await saveSop({
        id: sop?.id,
        title: title.trim(),
        symptoms: symptoms.trim(),
        body: body.trim(),
        reference: reference.trim(),
        steps: cleanSteps,
      });
      onSaved(saved);
      onOpenChange(false);
      toast.success(sop ? "SOP updated." : "SOP added.");
    } catch (err) {
      unstable_rethrow(err);
      toast.error(err instanceof Error ? err.message : "Failed to save SOP.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{sop ? "Edit SOP" : "Add SOP"}</DialogTitle>
          <DialogDescription>
            SOP documents are the reference for action recommendations. The
            chatbot&apos;s recommendations are drawn only from the SOPs saved here.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="sop-title">
              Title <span className="text-destructive">*</span>
            </Label>
            <Input
              id="sop-title"
              placeholder="e.g. Heat Dissipation Failure Handling"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="sop-symptoms">Symptoms / keywords</Label>
            <Textarea
              id="sop-symptoms"
              placeholder="e.g. high process temperature, hot machine, ineffective heat dissipation"
              value={symptoms}
              onChange={(e) => setSymptoms(e.target.value)}
              rows={2}
              className="resize-none"
            />
            <p className="text-muted-foreground text-xs">
              Used by the SOP search to match machine conditions.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="sop-body">
              Description &amp; actions <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="sop-body"
              placeholder="Explanation of the cause + outline of the handling steps…"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              className="resize-none"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="sop-reference">Reference</Label>
            <Input
              id="sop-reference"
              placeholder="e.g. Thermal Maintenance SOP - Rev.2"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </div>

          {/* Action steps */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Action steps</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setSteps((prev) => [...prev, emptyStep()])}
              >
                <Plus className="size-4" />
                Add step
              </Button>
            </div>
            <div className="flex flex-col gap-3">
              {steps.map((s, i) => (
                <div
                  key={s.id}
                  className="flex flex-col gap-2 rounded-lg border p-3"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground text-sm font-medium">
                      {i + 1}.
                    </span>
                    <Input
                      placeholder="Step description"
                      value={s.text}
                      onChange={(e) => updateStep(s.id, { text: e.target.value })}
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        setSteps((prev) => prev.filter((x) => x.id !== s.id))
                      }
                    >
                      <Trash2 className="size-4" />
                      <span className="sr-only">Remove step</span>
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-2 pl-6">
                    <Select
                      value={s.priority}
                      onValueChange={(v) => {
                        if (v) updateStep(s.id, { priority: v as SopStep["priority"] });
                      }}
                    >
                      <SelectTrigger className="w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="segera">Urgent</SelectItem>
                        <SelectItem value="terjadwal">Scheduled</SelectItem>
                      </SelectContent>
                    </Select>
                    <div className="flex items-center gap-1.5">
                      <Input
                        type="number"
                        min={0}
                        value={String(s.estimatedMinutes)}
                        onChange={(e) =>
                          updateStep(s.id, {
                            estimatedMinutes: Number(e.target.value),
                          })
                        }
                        className="w-20"
                      />
                      <span className="text-muted-foreground text-sm">min</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" onClick={handleSave} disabled={!canSave}>
            Save SOP
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
