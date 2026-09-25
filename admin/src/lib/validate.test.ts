import { describe, expect, it } from "vitest";
import { validateFleet } from "./validate";

const base = { depot_id: "depot_adyar", name: "Adyar Depot", lat: 13.0067, lon: 80.2532, fleet_size: 60, reserve: 4, out_of_service: 1 };

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
