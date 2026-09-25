import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { DecisionRequest, Recommendation, RouteEffect } from "../api/types";
import { hhmm, humanize, pct } from "../lib/format";
import { RejectModal } from "./RejectModal";
import { WhatIfPanel } from "./WhatIfPanel";

const ACTION: Record<Recommendation["action"], { icon: string; label: string }> = {
  move_bus: { icon: "⇄", label: "Move bus" },
  add_trip: { icon: "+", label: "Add trip" },
  release_bus: { icon: "↩", label: "Release bus" },
};

function routesLabel(r: Recommendation) {
  const from = r.from_route_id ?? "Depot reserve";
  const to = r.to_route_id ?? "Depot";
  return `${from} → ${to}`;
}

function EffectRow({ label, e }: { label: string; e?: RouteEffect }) {
  if (!e) return null;
  return (
    <tr>
      <td>{label}</td>
      <td className="num">
        {e.wait_min_before.toFixed(1)} → <b>{e.wait_min_after.toFixed(1)}</b> min
      </td>
      <td className="num">
        {pct(e.peak_load_before)} → <b>{pct(e.peak_load_after)}</b>
      </td>
    </tr>
  );
}

export function RecommendationCard({ rec }: { rec: Recommendation }) {
  const qc = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: (d: DecisionRequest) => api.decide(d),
    onSuccess: () => {
      setRejecting(false);
      qc.invalidateQueries({ queryKey: ["recommendations"] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        setRejecting(false);
        setNotice("Already decided by someone else. List refreshed.");
        qc.invalidateQueries({ queryKey: ["recommendations"] });
      } else {
        setNotice(err instanceof ApiError ? err.message : "Could not save the decision.");
      }
    },
  });

  const a = ACTION[rec.action];
  const pending = rec.status === "pending";

  const body = (
    <>
      <p className="explanation">{rec.explanation}</p>
      <table className="effect">
        <thead>
          <tr>
            <th />
            <th>Wait</th>
            <th>Peak load</th>
          </tr>
        </thead>
        <tbody>
          <EffectRow label={`Route ${rec.to_route_id ?? ""}`} e={rec.expected_effect.to_route} />
          <EffectRow label={`Route ${rec.from_route_id ?? ""}`} e={rec.expected_effect.from_route} />
        </tbody>
      </table>
      <div className="meta">
        <span className={`chip on conf-${rec.confidence}`}>{rec.confidence} confidence</span>
        <span className="chip off">Deadhead {rec.deadhead_km.toFixed(1)} km</span>
        <span className={`chip ${rec.solver === "greedy" ? "grey" : "off"}`} title="Optimiser used">
          {rec.solver === "greedy" ? "greedy fallback" : "CP-SAT"}
        </span>
        {rec.trigger_flags.map((f) => (
          <span key={f} className="chip off">
            {humanize(f)}
          </span>
        ))}
      </div>
      {notice && <p className="error">{notice}</p>}
      {pending && (
        <>
          <WhatIfPanel recommendationId={rec.id} />
          <div className="row end">
            <button
              type="button"
              className="danger"
              disabled={decide.isPending}
              onClick={() => {
                setNotice(null);
                setRejecting(true);
              }}
            >
              Reject
            </button>
            <button
              type="button"
              className="primary"
              disabled={decide.isPending}
              onClick={() => {
                setNotice(null);
                decide.mutate({ recommendation_id: rec.id, decision: "approve" });
              }}
            >
              Approve
            </button>
          </div>
        </>
      )}
    </>
  );

  const header = (
    <div className="rec-head">
      <span className="action-icon" aria-hidden>
        {a.icon}
      </span>
      <div>
        <strong>
          {a.label}
          {rec.bus_count > 1 ? ` ×${rec.bus_count}` : ""}: {routesLabel(rec)}
        </strong>
        <div className="muted small">
          {hhmm(rec.window_start)}–{hhmm(rec.window_end)} · {rec.id}
        </div>
      </div>
      {!pending && <span className={`status status-${rec.status}`}>{rec.status}</span>}
    </div>
  );

  return (
    <article className={`card rec rec-${rec.status}`} aria-label={`${a.label} ${routesLabel(rec)}`}>
      {rec.status === "expired" ? (
        <details>
          <summary>{header}</summary>
          {body}
        </details>
      ) : (
        <>
          {header}
          {body}
        </>
      )}
      {rejecting && (
        <RejectModal
          busy={decide.isPending}
          onCancel={() => setRejecting(false)}
          onSubmit={(reason, note) =>
            decide.mutate({ recommendation_id: rec.id, decision: "reject", reason, ...(note ? { note } : {}) })
          }
        />
      )}
    </article>
  );
}
