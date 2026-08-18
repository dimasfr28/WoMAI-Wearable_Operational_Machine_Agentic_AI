import type { RiskLevel } from "@/lib/types";

// Kelas warna badge risiko, dipakai konsisten di kartu prediksi, riwayat, dan halaman mesin
export const RISK_BADGE: Record<RiskLevel, string> = {
  tinggi: "bg-red-100 text-red-700",
  sedang: "bg-amber-100 text-amber-700",
  rendah: "bg-emerald-100 text-emerald-700",
};

// Display label for each RiskLevel — the underlying value stays as-is (it's
// also the literal the backend sends over the wire, see routes_chat.py's
// _risk_level()), only the text shown to users is translated here.
export const RISK_LABEL: Record<RiskLevel, string> = {
  tinggi: "High",
  sedang: "Medium",
  rendah: "Low",
};
