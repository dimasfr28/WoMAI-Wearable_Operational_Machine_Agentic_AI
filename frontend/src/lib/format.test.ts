import { describe, expect, it } from "vitest";
import { formatRupiah } from "./format";

describe("formatRupiah", () => {
  it("memformat jutaan dengan pemisah titik", () => {
    expect(formatRupiah(12500000)).toBe("Rp12.500.000");
  });

  it("memformat nol", () => {
    expect(formatRupiah(0)).toBe("Rp0");
  });

  it("membulatkan desimal", () => {
    expect(formatRupiah(1999.6)).toBe("Rp2.000");
  });
});
