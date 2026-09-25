import { describe, expect, it } from "vitest";
import { hhmm, LOAD_COLORS, loadBand, loadColor } from "./format";

describe("load colour thresholds", () => {
  it.each([
    [0, "ok"],
    [0.59, "ok"],
    [0.6, "busy"],
    [1.0, "busy"],
    [1.01, "over"],
    [1.25, "over"],
  ] as const)("load %s → %s", (lf, band) => {
    expect(loadBand(lf)).toBe(band);
  });

  it("dark buses are grey regardless of load", () => {
    expect(loadColor(1.5, true)).toBe(LOAD_COLORS.dark);
  });
});

describe("hhmm", () => {
  it("keeps the offset's local time", () => {
    expect(hhmm("2026-09-25T17:30:00+05:30")).toBe("17:30");
  });
});
