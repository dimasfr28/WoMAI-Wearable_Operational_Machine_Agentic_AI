/** Ringkas teks pesan pertama menjadi judul sesi. Fungsi murni, tanpa I/O. */
export function deriveTitle(text: string): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length === 0) return "New conversation";
  return clean.length > 40 ? clean.slice(0, 40).trimEnd() + "…" : clean;
}
