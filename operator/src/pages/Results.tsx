import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import { CHART, STRATEGY_COLOR } from "../lib/chart";
import { humanize } from "../lib/format";
import { errorLevelLabel, METRICS, robustness, waitByScenario } from "../lib/results";

const tick = { fill: CHART.muted, fontSize: 11 };

export function Results() {
  const q = useQuery({ queryKey: ["results"], queryFn: api.getResults, staleTime: Infinity });

  if (q.isPending) return <p className="muted pad">Loading scenario results…</p>;
  if (q.isError) return <p className="error pad">Could not load results.</p>;
  const res = q.data;
  if (!res.rows.length) return <p className="muted pad">No scenario results yet.</p>;

  const waits = waitByScenario(res);
  const robust = robustness(res);

  return (
    <div className="results pad">
      <section className="chart-box">
        <h3 className="chart-title">Average wait by scenario (min, lower is better)</h3>
        <p className="muted small">Perfect forecast (error level 0).</p>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={waits} margin={{ top: 8, right: 8, bottom: 0, left: -12 }} barGap={2}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="scenario" tickFormatter={humanize} tick={tick} stroke={CHART.axis} interval={0} />
            <YAxis tick={tick} stroke={CHART.axis} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(1)} min`} labelFormatter={(l) => humanize(String(l))} />
            <Legend wrapperStyle={{ fontSize: 12 }} formatter={humanize} />
            {res.strategies.map((s, i) => (
              <Bar
                key={s}
                dataKey={s}
                name={s}
                fill={STRATEGY_COLOR[s] ?? CHART.series[i % CHART.series.length]}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="chart-box">
        <h3 className="chart-title">AduthaBus wait reduction vs baseline, under forecast error (%)</h3>
        <p className="muted small">Averaged over all scenarios. How much of the gain survives a worse forecast.</p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={robust} margin={{ top: 20, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="level" tick={tick} stroke={CHART.axis} interval={0} />
            <YAxis tick={tick} stroke={CHART.axis} unit="%" />
            <Tooltip formatter={(v) => `${v}%`} />
            <Bar dataKey="gain" name="Wait reduction" fill={STRATEGY_COLOR.aduthabus} radius={[4, 4, 0, 0]}>
              <LabelList dataKey="gain" position="top" formatter={(v: unknown) => (v == null ? "" : `${v}%`)} style={{ fill: "var(--text-2)", fontSize: 11 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section>
        <h3 className="chart-title">All metrics</h3>
        <div className="table-scroll">
          <table className="metrics">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Strategy</th>
                <th>Forecast</th>
                {METRICS.map((m) => (
                  <th key={m.key} title={m.direction}>
                    {m.label}
                    <br />
                    <small className="muted">{m.direction}</small>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {res.rows.map((r, i) => (
                <tr key={i}>
                  <td>{humanize(r.scenario)}</td>
                  <td>{humanize(r.strategy)}</td>
                  <td>{errorLevelLabel(r.error_level)}</td>
                  {METRICS.map((m) => (
                    <td key={m.key} className="num">
                      {Number.isInteger(r[m.key]) ? r[m.key] : r[m.key].toFixed(2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
