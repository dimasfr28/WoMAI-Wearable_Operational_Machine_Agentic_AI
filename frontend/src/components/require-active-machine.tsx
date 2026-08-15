"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useActiveMachine } from "@/hooks/use-active-machine";
import type { Machine } from "@/lib/types";

interface RequireActiveMachineProps {
  children: (machine: Machine) => React.ReactNode;
}

/** Gate client-side (rancangan.txt Section 2): mesin harus dipilih di /mesin
 * sebelum mengakses New Consultation/Machine Diagnosis/Machine Report/
 * Knowledge Base. Middleware.ts tidak bisa melakukan ini sendiri (edge
 * runtime, tidak ada akses localStorage) — makanya ini murni client
 * component, dijalankan setelah render pertama. */
export function RequireActiveMachine({ children }: RequireActiveMachineProps) {
  const { machine, loading } = useActiveMachine();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !machine) {
      router.replace("/mesin");
    }
  }, [loading, machine, router]);

  if (loading || !machine) {
    return null;
  }

  return <>{children(machine)}</>;
}
