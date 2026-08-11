import { describe, expect, it } from "vitest";
import { deriveTitle } from "./title";

// Persistensi kini di Postgres (Supabase) via server actions — tidak lagi
// diuji terhadap localStorage. Hanya helper murni yang diuji di sini.
describe("deriveTitle", () => {
  it("memotong 40 karakter dengan elipsis", () => {
    const long =
      "motor line 3 suhu prosesnya 310K torsi 45 Nm sudah dipakai 200 menit";
    const title = deriveTitle(long);
    expect(title.length).toBeLessThanOrEqual(41);
    expect(title.endsWith("…")).toBe(true);
  });

  it("teks pendek apa adanya", () => {
    expect(deriveTitle("suhu tinggi")).toBe("suhu tinggi");
  });

  it("fallback untuk teks kosong", () => {
    expect(deriveTitle("   ")).toBe("Percakapan baru");
  });
});
