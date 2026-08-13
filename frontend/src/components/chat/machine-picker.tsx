"use client";

import { useState } from "react";
import { Factory } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
} from "@/components/ui/select";
import { MachineFormDialog } from "@/components/machine-form-dialog";
import { useMachines } from "@/hooks/use-machines";
import type { Machine } from "@/lib/types";

interface MachinePickerProps {
  value: Machine | null;
  onChange: (m: Machine | null) => void;
  disabled?: boolean;
}

export function MachinePicker({
  value,
  onChange,
  disabled,
}: MachinePickerProps) {
  const { machines } = useMachines();
  const [openForm, setOpenForm] = useState(false);

  return (
    <>
      <Select
        value={value?.id ?? ""}
        onValueChange={(v) => {
          if (!v) return;
          if (v === "__add__") {
            setOpenForm(true);
            return;
          }
          onChange(machines.find((m) => m.id === v) ?? null);
        }}
        disabled={disabled}
      >
        <SelectTrigger className="w-[170px] max-sm:w-[130px]">
          <Factory className="size-4 shrink-0 text-muted-foreground" />
          {/* Render name directly — Base UI SelectValue can't read ItemText
              when the popup is unmounted (closed), so we bypass it */}
          <span
            data-slot="select-value"
            className={cn(
              "flex flex-1 truncate text-left",
              !value && "text-muted-foreground",
            )}
          >
            {value?.name ?? "Pilih mesin"}
          </span>
        </SelectTrigger>
        <SelectContent>
          {machines.map((m) => (
            <SelectItem key={m.id} value={m.id}>
              <span className="flex-1 truncate">{m.name}</span>
              <Badge
                variant="outline"
                className="ml-1 shrink-0 px-1 py-0 text-[10px] leading-4"
              >
                {m.machineType ?? "Haas"}
              </Badge>
            </SelectItem>
          ))}
          {machines.length > 0 && <SelectSeparator />}
          <SelectItem value="__add__">+ Tambah mesin</SelectItem>
        </SelectContent>
      </Select>
      <MachineFormDialog
        open={openForm}
        onOpenChange={setOpenForm}
        onSaved={(m) => onChange(m)}
      />
    </>
  );
}
