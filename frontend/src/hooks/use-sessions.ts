"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { loadSessions, SESSIONS_CHANGED_EVENT } from "@/lib/storage";
import type { ChatSession } from "@/lib/types";

export function useSessions() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      loadSessions()
        .then((loaded) => {
          if (active) setSessions(loaded);
        })
        .catch(() => {
          if (active) toast.error("Gagal memuat riwayat percakapan.");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    };
    refresh();
    window.addEventListener(SESSIONS_CHANGED_EVENT, refresh);
    return () => {
      active = false;
      window.removeEventListener(SESSIONS_CHANGED_EVENT, refresh);
    };
  }, []);

  return { sessions, loading };
}
