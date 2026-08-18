import { describe, expect, it } from "vitest";
import {
  formatManualMessage,
  parseManualInput,
  pickScenario,
} from "./scenarios";

describe("pickScenario: kata kunci", () => {
  it("mendeteksi HDF dari kata suhu", () => {
    expect(pickScenario("motor line 3 temperature is running very high").key).toBe("hdf");
  });

  it("mendeteksi OSF dari kata torsi", () => {
    expect(pickScenario("torque keeps rising since this morning").key).toBe("osf");
  });

  it("mendeteksi TWF dari kata aus", () => {
    expect(pickScenario("the tool is worn out from long use").key).toBe("twf");
  });

  it("mendeteksi PWF dari kata daya", () => {
    expect(pickScenario("machine power is unstable").key).toBe("pwf");
  });

  it("default ke skenario normal", () => {
    expect(pickScenario("machine running as usual").key).toBe("none");
  });

  it("tidak sensitif kapital", () => {
    expect(pickScenario("TEMPERATURE VERY HOT").key).toBe("hdf");
  });
});

describe("input manual", () => {
  const params = {
    type: "M" as const,
    airTemp: 300,
    processTemp: 312,
    rpm: 1500,
    torque: 45,
    toolWear: 120,
  };

  it("round-trip format lalu parse", () => {
    expect(parseManualInput(formatManualMessage(params))).toEqual(params);
  });

  it("mengembalikan null untuk teks biasa", () => {
    expect(parseManualInput("temperature is high")).toBeNull();
  });

  it("suhu proses >= 311 K -> hdf", () => {
    expect(pickScenario(formatManualMessage(params)).key).toBe("hdf");
  });

  it("torsi >= 60 Nm -> osf", () => {
    expect(
      pickScenario(
        formatManualMessage({ ...params, processTemp: 309, torque: 65 }),
      ).key,
    ).toBe("osf");
  });

  it("tool wear >= 200 min -> twf", () => {
    expect(
      pickScenario(
        formatManualMessage({ ...params, processTemp: 309, toolWear: 210 }),
      ).key,
    ).toBe("twf");
  });

  it("rpm < 1300 -> pwf", () => {
    expect(
      pickScenario(
        formatManualMessage({ ...params, processTemp: 309, rpm: 1250 }),
      ).key,
    ).toBe("pwf");
  });

  it("parameter normal -> none", () => {
    expect(
      pickScenario(formatManualMessage({ ...params, processTemp: 309 })).key,
    ).toBe("none");
  });
});
