"use client";

import { useEffect, useState } from "react";
import { unstable_rethrow } from "next/navigation";
import { toast } from "sonner";
import { loadSops, SOPS_CHANGED_EVENT } from "@/lib/sops";
import type { Sop } from "@/lib/types";

export function useSops() {
  const [sops, setSops] = useState<Sop[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      loadSops()
        .then((loaded) => {
          if (active) setSops(loaded);
        })
        .catch((err) => {
          unstable_rethrow(err);
          if (active) toast.error("Failed to load SOP list.");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    };
    refresh();
    window.addEventListener(SOPS_CHANGED_EVENT, refresh);
    return () => {
      active = false;
      window.removeEventListener(SOPS_CHANGED_EVENT, refresh);
    };
  }, []);

  return { sops, loading };
}
