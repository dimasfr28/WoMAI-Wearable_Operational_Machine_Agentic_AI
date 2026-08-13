"use client";

import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
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
import {
  formatManualMessage,
  type ManualParams,
} from "@/lib/mock/scenarios";

interface ManualInputDialogProps {
  disabled: boolean;
  onSend: (text: string) => void;
  defaultType?: "L" | "M" | "H";
}

const NUMERIC_FIELDS: {
  key: Exclude<keyof ManualParams, "type">;
  label: string;
  placeholder: string;
}[] = [
  { key: "airTemp", label: "Suhu udara [K]", placeholder: "300" },
  { key: "processTemp", label: "Suhu proses [K]", placeholder: "310" },
  { key: "rpm", label: "Kecepatan putar [rpm]", placeholder: "1500" },
  { key: "torque", label: "Torsi [Nm]", placeholder: "40" },
  { key: "toolWear", label: "Tool wear [min]", placeholder: "120" },
];

export function ManualInputDialog({
  disabled,
  onSend,
  defaultType,
}: ManualInputDialogProps) {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<ManualParams["type"]>(defaultType ?? "M");
  const [values, setValues] = useState<Record<string, string>>({});

  const complete =
    NUMERIC_FIELDS.every((f) =>
      Number.isFinite(Number(values[f.key] ?? "")),
    ) &&
    NUMERIC_FIELDS.every(
      (f) => values[f.key] !== undefined && values[f.key] !== "",
    );

  function submit() {
    if (!complete) return;
    onSend(
      formatManualMessage({
        type,
        airTemp: Number(values.airTemp),
        processTemp: Number(values.processTemp),
        rpm: Number(values.rpm),
        torque: Number(values.torque),
        toolWear: Number(values.toolWear),
      }),
    );
    setOpen(false);
    setValues({});
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) setType(defaultType ?? "M"); }}>
      {/* Base UI uses render prop instead of asChild */}
      <DialogTrigger
        disabled={disabled}
        render={
          <Button type="button" variant="outline" size="icon" />
        }
      >
        <SlidersHorizontal className="size-4" />
        <span className="sr-only">Input Manual</span>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Input Manual Parameter Mesin</DialogTitle>
          <DialogDescription>
            Isi 6 parameter sensor bila deskripsi bahasa natural kurang
            meyakinkan.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="tipe-mesin">Tipe mesin</Label>
            <Select
              value={type}
              onValueChange={(v) => {
                if (v) setType(v as ManualParams["type"]);
              }}
            >
              <SelectTrigger id="tipe-mesin" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="L">L (Low)</SelectItem>
                <SelectItem value="M">M (Medium)</SelectItem>
                <SelectItem value="H">H (High)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {NUMERIC_FIELDS.map((f) => (
            <div key={f.key} className="flex flex-col gap-2">
              <Label htmlFor={f.key}>{f.label}</Label>
              <Input
                id={f.key}
                type="number"
                inputMode="decimal"
                placeholder={f.placeholder}
                value={values[f.key] ?? ""}
                onChange={(e) =>
                  setValues((prev) => ({ ...prev, [f.key]: e.target.value }))
                }
              />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button type="button" onClick={submit} disabled={!complete}>
            Kirim ke Chatbot
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
