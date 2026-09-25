import { useState } from "react";
import { FLAG_NAMES, type FlagName, type Route, type RouteHealth } from "../api/types";
import { humanize } from "../lib/format";

const FLAG_LABEL: Record<FlagName, string> = {
  overcrowded: "Crowded",
  underused: "Underused",
  delay_emerging: "Delay",
  bunching: "Bunching",
};

interface Props {
  health: RouteHealth[];
  routes: Route[];
  selected?: string | null;
  onSelect: (routeId: string) => void;
}

export function RouteHealthTable({ health, routes, selected, onSelect }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const byId = new Map(routes.map((r) => [r.id, r]));

  if (!health.length) return <p className="muted pad">No route health yet.</p>;

  return (
    <table className="health">
      <thead>
        <tr>
          <th>Route</th>
          <th>Dir</th>
          <th>Flags</th>
        </tr>
      </thead>
      <tbody>
        {health.map((h) => {
          const key = `${h.route_id}:${h.direction}`;
          const route = byId.get(h.route_id);
          return (
            <tr
              key={key}
              className={selected === h.route_id ? "selected" : ""}
              onClick={() => onSelect(h.route_id)}
            >
              <td>
                <span className="swatch" style={{ background: route?.color ?? "#999" }} />
                {h.route_id}
              </td>
              <td>{h.direction}</td>
              <td>
                <div className="chips">
                  {FLAG_NAMES.map((name) => {
                    const f = h.flags[name];
                    if (!f) return null;
                    const chipKey = `${key}:${name}`;
                    const tip = `${humanize(name)} · ${f.on ? "ON" : "off"} · confidence ${f.confidence}${
                      f.evidence ? `\n${f.evidence}` : ""
                    }`;
                    return (
                      <button
                        key={name}
                        type="button"
                        className={`chip ${f.on ? `on conf-${f.confidence}` : "off"}`}
                        title={tip}
                        aria-expanded={open === chipKey}
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpen(open === chipKey ? null : chipKey);
                        }}
                      >
                        {FLAG_LABEL[name]}
                        {f.on && <small> · {f.confidence}</small>}
                      </button>
                    );
                  })}
                </div>
                {FLAG_NAMES.map((name) => {
                  const f = h.flags[name];
                  return open === `${key}:${name}` && f ? (
                    <p key={name} className="evidence">
                      <b>{humanize(name)}</b> ({f.confidence} confidence): {f.evidence ?? "No evidence recorded."}
                    </p>
                  ) : null;
                })}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
