"use server";

import { randomUUID } from "node:crypto";
import { requireSession } from "@/lib/auth/session";
import type { Sop, SopMode, SopStep } from "@/lib/types";

// Data contoh in-memory — lihat catatan yang sama di actions/machines.ts.
// Isi diadaptasi dari knowledge base SOP nyata comfest-18/wo_m_ai backend.
let sopsStore: Sop[] = [
  {
    id: "sop-demo-hdf",
    mode: "HDF",
    title: "Penanganan Heat Dissipation Failure",
    symptoms:
      "suhu proses tinggi, selisih suhu udara-proses menyempit, mesin terasa panas, overheat",
    body:
      "Heat Dissipation Failure terjadi ketika perbedaan suhu udara dan proses turun di bawah 8.6 K pada kecepatan putar rendah, sehingga panas tidak terbuang.",
    steps: [
      {
        id: "hdf-1",
        text: "Turunkan beban mesin ke <=50% dan pantau tren suhu proses",
        priority: "segera",
        estimatedMinutes: 10,
      },
      {
        id: "hdf-2",
        text: "Periksa dan bersihkan sistem pendingin (kipas, heatsink, saluran udara)",
        priority: "segera",
        estimatedMinutes: 15,
      },
      {
        id: "hdf-3",
        text: "Inspeksi termal menyeluruh pada bearing dan gearbox",
        priority: "terjadwal",
        estimatedMinutes: 45,
      },
    ],
    reference: "SOP Maintenance Termal - Rev.2",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "sop-demo-osf",
    mode: "OSF",
    title: "Penanganan Overstrain Failure",
    symptoms:
      "torsi tinggi, beban berat, tool wear menumpuk, mesin terasa berat, overstrain",
    body:
      "Overstrain Failure terjadi saat hasil kali tool wear dan torque melewati ambang aman material.",
    steps: [
      {
        id: "osf-1",
        text: "Kurangi torsi operasi di bawah ambang aman tipe material",
        priority: "segera",
        estimatedMinutes: 5,
      },
      {
        id: "osf-2",
        text: "Inspeksi visual tool dan komponen transmisi dari deformasi",
        priority: "segera",
        estimatedMinutes: 20,
      },
      {
        id: "osf-3",
        text: "Ganti tool bila tool wear melebihi 200 menit",
        priority: "terjadwal",
        estimatedMinutes: 30,
      },
    ],
    reference: "SOP Beban & Transmisi - Rev.1",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
];

export async function loadSopsAction(): Promise<Sop[]> {
  await requireSession();
  return sopsStore;
}

export async function saveSopAction(input: {
  id?: string;
  mode: SopMode;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStep[];
  reference: string;
}): Promise<Sop> {
  await requireSession();
  const now = new Date().toISOString();

  if (input.id) {
    const idx = sopsStore.findIndex((s) => s.id === input.id);
    if (idx >= 0) {
      const updated: Sop = {
        ...sopsStore[idx],
        ...input,
        id: input.id,
        updatedAt: now,
      };
      sopsStore = [
        ...sopsStore.slice(0, idx),
        updated,
        ...sopsStore.slice(idx + 1),
      ];
      return updated;
    }
  }

  const sop: Sop = {
    id: input.id ?? randomUUID(),
    mode: input.mode,
    title: input.title,
    symptoms: input.symptoms,
    body: input.body,
    steps: input.steps,
    reference: input.reference,
    createdAt: now,
    updatedAt: now,
  };
  sopsStore = [...sopsStore, sop];
  return sop;
}

export async function deleteSopAction(id: string): Promise<void> {
  await requireSession();
  sopsStore = sopsStore.filter((s) => s.id !== id);
}
