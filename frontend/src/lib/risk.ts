import type { RiskLevel } from "@/lib/types";

// Kelas warna badge risiko, dipakai konsisten di kartu prediksi, riwayat, dan halaman mesin
export const RISK_BADGE: Record<RiskLevel, string> = {
  tinggi: "bg-red-100 text-red-700",
  sedang: "bg-amber-100 text-amber-700",
  rendah: "bg-emerald-100 text-emerald-700",
};
