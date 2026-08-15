"use client";

// Mesin aktif global (rancangan.txt Section 2: user WAJIB memilih mesin
// spesifik setelah login sebelum mengakses New Consultation/Machine
// Diagnosis/Machine Report/Knowledge Base). Disimpan di localStorage —
// murni client-side, TIDAK diverifikasi di middleware (yang berjalan di
// edge tanpa akses localStorage) — guard-nya ada di RequireActiveMachine
// (client component), bukan di middleware.ts.

const STORAGE_KEY = "womai:active-machine-id";
export const ACTIVE_MACHINE_CHANGED_EVENT = "womai:active-machine-changed";

export function getActiveMachineId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

export function setActiveMachineId(id: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, id);
  window.dispatchEvent(new Event(ACTIVE_MACHINE_CHANGED_EVENT));
}

export function clearActiveMachineId(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event(ACTIVE_MACHINE_CHANGED_EVENT));
}
