import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, downloadDecisionsCsv } from "../api/client";
import type { RecommendationStatus } from "../api/types";
import type { Cycle } from "../hooks/useCycle";
import { RecommendationCard } from "./RecommendationCard";

const FILTERS: { value: RecommendationStatus | ""; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "expired", label: "Expired" },
  { value: "", label: "All" },
];

export function RecommendationQueue({ cycle }: { cycle: Cycle }) {
  const [status, setStatus] = useState<RecommendationStatus | "">("pending");
  const [csvError, setCsvError] = useState<string | null>(null);

  const recs = useQuery({
    queryKey: ["recommendations", status],
    queryFn: () => api.getRecommendations(status || undefined),
    refetchInterval: 10_000,
  });

  async function exportCsv() {
    setCsvError(null);
    try {
      await downloadDecisionsCsv();
    } catch (err) {
      setCsvError(err instanceof ApiError ? err.message : "Export failed");
    }
  }

  return (
    <div className="queue">
      <div className="toolbar">
        <button type="button" className="primary" onClick={cycle.run} disabled={cycle.running || !cycle.ready}>
          {cycle.running ? "Solving…" : "Run cycle"}
        </button>
        {cycle.running && <div className="spinner small" aria-label="Optimiser running" />}
        <select value={status} onChange={(e) => setStatus(e.target.value as RecommendationStatus | "")} aria-label="Filter by status">
          {FILTERS.map((f) => (
            <option key={f.label} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
        <button type="button" onClick={exportCsv}>
          Export CSV
        </button>
      </div>
      {cycle.error && <p className="error pad">Cycle failed: {(cycle.error as Error).message}</p>}
      {cycle.lastRan && !cycle.lastRan.ran && (
        <p className="muted small pad">Last cycle was under 15 simulated minutes ago; showing cached plan.</p>
      )}
      {csvError && <p className="error pad">{csvError}</p>}

      {recs.isPending && <p className="muted pad">Loading recommendations…</p>}
      {recs.isError && <p className="error pad">Could not load recommendations.</p>}
      {recs.data?.length === 0 && (
        <p className="muted pad">No {status || ""} recommendations. The network looks balanced, or run a cycle.</p>
      )}
      {recs.data?.map((r) => <RecommendationCard key={r.id} rec={r} />)}
    </div>
  );
}
