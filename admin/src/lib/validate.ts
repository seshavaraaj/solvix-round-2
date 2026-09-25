import type { FleetConfig, Route } from "../api/types";

/** Returns an error message, or null when the fleet config is valid. */
export function validateFleet(f: FleetConfig): string | null {
  const nums = [f.fleet_size, f.reserve, f.out_of_service];
  if (nums.some((n) => !Number.isInteger(n) || n < 0)) return "Counts must be whole numbers ≥ 0.";
  if (f.reserve + f.out_of_service > f.fleet_size) return "Reserve + out of service cannot exceed fleet size.";
  return null;
}

export function validateRoute(r: Route): string | null {
  if (!r.name.trim()) return "Name is required.";
  if (!r.depot_id.trim()) return "Depot is required.";
  if (!Number.isFinite(r.min_headway_min) || r.min_headway_min <= 0) return "Minimum headway must be > 0 minutes.";
  if (!/^#[0-9a-fA-F]{6}$/.test(r.color)) return "Colour must be a hex value like #E4572E.";
  return null;
}
