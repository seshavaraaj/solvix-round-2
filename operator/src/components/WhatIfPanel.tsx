import { useEffect, useRef, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, ApiError } from "../api/client";
import type { WhatIfMetrics, WhatIfResult } from "../api/types";
import { hhmm, pct } from "../lib/format";
import { CHART } from "../lib/chart";

const TIMEOUT_MS = 30_000;

const METRICS: { key: keyof WhatIfMetrics; label: string; fmt: (x: number) => string }[] = [
  { key: "avg_wait_min", label: "Avg wait", fmt: (x) => `${x.toFixed(1)} min` },
  { key: "p95_wait_min", label: "P95 wait", fmt: (x) => `${x.toFixed(1)} min` },
  { key: "left_behind", label: "Left behind", fmt: (x) => String(Math.round(x)) },
  { key: "overload_min", label: "Overload", fmt: (x) => `${Math.round(x)} min` },
  { key: "bunching_events", label: "Bunching", fmt: (x) => String(Math.round(x)) },
];

type State =
  | { kind: "idle" }
  | { kind: "running"; started: number }
  | { kind: "done"; result: WhatIfResult }
  | { kind: "error"; message: string };

export function WhatIfPanel({ recommendationId }: { recommendationId: string }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (state.kind !== "running") return;
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - state.started) / 1000)), 500);
    return () => clearInterval(id);
  }, [state]);

  async function simulate() {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      ctrl.abort();
    }, TIMEOUT_MS);
    setElapsed(0);
    setState({ kind: "running", started: Date.now() });
    try {
      const result = await api.whatIf(recommendationId, ctrl.signal);
      setState({ kind: "done", result });
    } catch (err) {
      if (!timedOut && (err as Error).name === "AbortError") return;
      setState({
        kind: "error",
        message: timedOut
          ? "Simulation took longer than 30 s."
          : err instanceof ApiError
            ? err.message
            : "Simulation failed.",
      });
    } finally {
      clearTimeout(timer);
    }
  }

  if (state.kind === "idle")
    return (
      <button type="button" onClick={simulate}>
        Simulate
      </button>
    );

  if (state.kind === "running")
    return (
      <div className="whatif running" role="status">
        <div className="spinner small" aria-hidden /> Simulating 2 hours… {elapsed}s
      </div>
    );

  if (state.kind === "error")
    return (
      <div className="whatif">
        <p className="error">{state.message}</p>
        <button type="button" onClick={simulate}>
          Retry
        </button>
      </div>
    );

  const r = state.result;
  const series = r.series.map((p) => ({ t: hhmm(p.t), without: p.load_without, with: p.load_with }));
  return (
    <div className="whatif">
      <table className="compare">
        <thead>
          <tr>
            <th>{r.horizon_min} min horizon</th>
            <th>Without</th>
            <th>With</th>
          </tr>
        </thead>
        <tbody>
          {METRICS.map((m) => {
            const better = r.with[m.key] < r.without[m.key];
            return (
              <tr key={m.key}>
                <td>{m.label}</td>
                <td className="num">{m.fmt(r.without[m.key])}</td>
                <td className={`num ${better ? "better" : ""}`}>{m.fmt(r.with[m.key])}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {series.length > 1 && (
        <div className="chart-box" aria-label="Load on the target route with and without the change">
          <p className="chart-title">Peak load, with vs without</p>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="t" tick={{ fill: CHART.muted, fontSize: 11 }} stroke={CHART.axis} />
              <YAxis tickFormatter={pct} tick={{ fill: CHART.muted, fontSize: 11 }} stroke={CHART.axis} />
              <Tooltip formatter={(v) => pct(Number(v))} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="without" name="Without" stroke={CHART.series[1]} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="with" name="With" stroke={CHART.series[0]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="muted small">
        Ran in {r.runtime_s.toFixed(1)} s ·{" "}
        <button type="button" className="link" onClick={simulate}>
          run again
        </button>
      </p>
    </div>
  );
}
