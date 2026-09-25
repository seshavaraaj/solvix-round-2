import { useClock, useClockCommand } from "../hooks/useClock";
import { SCENARIOS, type Scenario, type Speed } from "../api/types";
import { hhmm, humanize } from "../lib/format";

const SPEEDS: Speed[] = [1, 10, 30];

export function ClockBar({ t }: { t?: string }) {
  const clock = useClock();
  const cmd = useClockCommand();
  const c = clock.data;
  const shownT = t ?? c?.t;

  if (clock.isError && !c) return <div className="clockbar muted">Clock unavailable</div>;
  if (!c) return <div className="clockbar muted">Loading clock…</div>;

  return (
    <div className="clockbar">
      <span className="clock-time" title={shownT}>
        {shownT ? hhmm(shownT) : "--:--"}
      </span>
      <button
        onClick={() => cmd.mutate({ action: c.playing ? "pause" : "play", speed: c.speed })}
        disabled={cmd.isPending}
        aria-label={c.playing ? "Pause replay" : "Play replay"}
      >
        {c.playing ? "❚❚ Pause" : "▶ Play"}
      </button>
      <div className="seg" role="group" aria-label="Replay speed">
        {SPEEDS.map((s) => (
          <button
            key={s}
            className={s === c.speed ? "on" : ""}
            aria-pressed={s === c.speed}
            disabled={cmd.isPending}
            onClick={() => cmd.mutate({ action: c.playing ? "play" : "pause", speed: s })}
          >
            ×{s}
          </button>
        ))}
      </div>
      <label className="scenario">
        Scenario
        <select
          value={c.scenario}
          disabled={cmd.isPending}
          onChange={(e) => cmd.mutate({ action: "jump", scenario: e.target.value as Scenario })}
        >
          {SCENARIOS.map((s) => (
            <option key={s} value={s}>
              {humanize(s)}
            </option>
          ))}
        </select>
      </label>
      {cmd.isError && <span className="error">Clock command failed</span>}
    </div>
  );
}
