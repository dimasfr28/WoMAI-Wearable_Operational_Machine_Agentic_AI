export function formatRupiah(amount: number): string {
  const rounded = Math.round(amount).toString();
  return "Rp" + rounded.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}
