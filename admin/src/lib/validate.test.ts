import { describe, expect, it } from "vitest";
import { validateFleet } from "./validate";

const base = { depot_id: "depot_okhla", name: "Okhla Depot", lat: 28.53, lon: 77.27, fleet_size: 60, reserve: 4, out_of_service: 1 };

describe("validateFleet", () => {
  it("accepts reserve + out_of_service ≤ fleet_size", () => {
    expect(validateFleet(base)).toBeNull();
    expect(validateFleet({ ...base, reserve: 59, out_of_service: 1 })).toBeNull();
  });
  it("rejects reserve + out_of_service > fleet_size", () => {
    expect(validateFleet({ ...base, reserve: 60, out_of_service: 1 })).toMatch(/cannot exceed/);
  });
  it("rejects negatives and fractions", () => {
    expect(validateFleet({ ...base, reserve: -1 })).not.toBeNull();
    expect(validateFleet({ ...base, fleet_size: 10.5 })).not.toBeNull();
  });
});
