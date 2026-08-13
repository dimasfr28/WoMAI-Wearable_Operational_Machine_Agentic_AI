"use client";

import { useEffect, useState } from "react";
import { unstable_rethrow } from "next/navigation";
import { toast } from "sonner";
import { loadMachines, MACHINES_CHANGED_EVENT } from "@/lib/machines";
import type { Machine } from "@/lib/types";

export function useMachines() {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      loadMachines()
        .then((loaded) => {
          if (active) setMachines(loaded);
        })
        .catch((err) => {
          unstable_rethrow(err);
          if (active) toast.error("Gagal memuat daftar mesin.");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    };
    refresh();
    window.addEventListener(MACHINES_CHANGED_EVENT, refresh);
    return () => {
      active = false;
      window.removeEventListener(MACHINES_CHANGED_EVENT, refresh);
    };
  }, []);

  return { machines, loading };
}
