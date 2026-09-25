import type { ErrorLevel, ScenarioResult, ScenarioRow } from "../api/types";

export type MetricKey = Exclude<keyof ScenarioRow, "scenario" | "strategy" | "error_level">;

/** Metric directions from solution2 §6.11. */
export const METRICS: { key: MetricKey; label: string; direction: string }[] = [
  { key: "avg_wait_min", label: "Avg wait (min)", direction: "lower is better" },
  { key: "p95_wait_min", label: "P95 wait (min)", direction: "lower is better" },
  { key: "left_behind", label: "Left behind", direction: "lower is better" },
  { key: "overload_min", label: "Overload (min)", direction: "lower is better" },
  { key: "bunching_events", label: "Bunching", direction: "lower is better" },
  { key: "avg_load_factor", label: "Avg load", direction: "higher is better, up to comfort limit" },
  { key: "deadhead_km", label: "Deadhead (km)", direction: "lower is better" },
  { key: "changes_per_hour", label: "Changes / h", direction: "within the limit" },
];

export const sameLevel = (a: ErrorLevel, b: ErrorLevel) => String(a) === String(b);

export function errorLevelLabel(l: ErrorLevel): string {
  if (l === "missed_surge") return "Missed surge";
  const n = Number(l);
  return n === 0 ? "Perfect forecast" : `±${Math.round(n * 100)}% error`;
}

/** Avg wait per scenario, one column per strategy, at forecast error level 0. */
export function waitByScenario(res: ScenarioResult) {
  return res.scenarios.map((scenario) => {
    const row: Record<string, string | number> = { scenario };
    for (const strategy of res.strategies) {
      const r = res.rows.find((x) => x.scenario === scenario && x.strategy === strategy && sameLevel(x.error_level, 0));
      if (r) row[strategy] = r.avg_wait_min;
    }
    return row;
  });
}

/**
 * TransitPulse avg-wait reduction vs baseline (%), averaged over scenarios, per error level.
 * Baseline does not use the forecast, so if it is missing at an error level its level-0 run is used.
 */
export function robustness(res: ScenarioResult) {
  return res.error_levels.map((level) => {
    const gains: number[] = [];
    for (const scenario of res.scenarios) {
      const tp = res.rows.find((x) => x.scenario === scenario && x.strategy === "transitpulse" && sameLevel(x.error_level, level));
      const base =
        res.rows.find((x) => x.scenario === scenario && x.strategy === "baseline" && sameLevel(x.error_level, level)) ??
        res.rows.find((x) => x.scenario === scenario && x.strategy === "baseline" && sameLevel(x.error_level, 0));
      if (tp && base && base.avg_wait_min > 0) gains.push(((base.avg_wait_min - tp.avg_wait_min) / base.avg_wait_min) * 100);
    }
    const gain = gains.length ? gains.reduce((a, b) => a + b, 0) / gains.length : null;
    return { level: errorLevelLabel(level), gain: gain === null ? null : Math.round(gain * 10) / 10 };
  });
}
