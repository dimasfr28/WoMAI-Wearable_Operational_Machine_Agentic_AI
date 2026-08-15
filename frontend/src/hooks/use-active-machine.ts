"use client";

import { useEffect, useState } from "react";
import {
  ACTIVE_MACHINE_CHANGED_EVENT,
  getActiveMachineId,
  setActiveMachineId as setActiveMachineIdStorage,
} from "@/lib/active-machine";
import { useMachines } from "@/hooks/use-machines";
import type { Machine } from "@/lib/types";

interface UseActiveMachineResult {
  machine: Machine | null;
  machineId: string | null;
  loading: boolean;
  setActiveMachine: (m: Machine) => void;
}

/** Mesin aktif global, divalidasi terhadap daftar mesin sungguhan dari backend
 * — kalau id tersimpan mengacu ke mesin yang sudah dihapus, `machine` jatuh ke
 * `null` (RequireActiveMachine lalu redirect balik ke /mesin). */
export function useActiveMachine(): UseActiveMachineResult {
  const { machines, loading: machinesLoading } = useMachines();
  const [machineId, setMachineId] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => setMachineId(getActiveMachineId());
    sync();
    window.addEventListener(ACTIVE_MACHINE_CHANGED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(ACTIVE_MACHINE_CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const machine = machineId
    ? (machines.find((m) => m.id === machineId) ?? null)
    : null;

  return {
    machine,
    machineId,
    loading: machinesLoading,
    setActiveMachine: (m: Machine) => {
      setActiveMachineIdStorage(m.id);
      setMachineId(m.id);
    },
  };
}
