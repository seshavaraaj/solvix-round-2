import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, ApiError, downloadDecisionsCsv } from "../api/client";

const PAGE = 25;

function when(iso: string) {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(iso);
  return m ? `${m[1]} ${m[2]}` : iso;
}

export function DecisionsPage() {
  const [page, setPage] = useState(0);
  const [csvError, setCsvError] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["decisions", page],
    queryFn: () => api.getDecisions(PAGE, page * PAGE),
    placeholderData: keepPreviousData,
  });

  async function exportCsv() {
    setCsvError(null);
    try {
      await downloadDecisionsCsv();
    } catch (err) {
      setCsvError(err instanceof ApiError ? err.message : "Export failed");
    }
  }

  const rows = q.data ?? [];
  return (
    <div className="page">
      <div className="row">
        <h2>Decision log</h2>
        <button type="button" onClick={exportCsv} style={{ marginLeft: "auto" }}>
          Export CSV
        </button>
      </div>
      {csvError && <p className="error">{csvError}</p>}
      {q.isPending && <p className="muted">Loading decisions…</p>}
      {q.isError && <p className="error">Could not load decisions: {(q.error as Error).message}</p>}
      {q.isSuccess && rows.length === 0 && <p className="muted">{page === 0 ? "No decisions yet." : "No more decisions."}</p>}
      {rows.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Recommendation</th>
              <th>Decision</th>
              <th>Reason</th>
              <th>Note</th>
              <th>By</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={`${d.recommendation_id}-${d.decided_at}`}>
                <td>{when(d.decided_at)}</td>
                <td>{d.recommendation_id}</td>
                <td className={d.decision === "approve" ? "ok" : "error"}>{d.decision}</td>
                <td>{d.reason?.replace(/_/g, " ") ?? "–"}</td>
                <td>{d.note ?? ""}</td>
                <td>{d.decided_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="row end">
        <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>
          ← Newer
        </button>
        <span className="muted">Page {page + 1}</span>
        <button type="button" disabled={rows.length < PAGE} onClick={() => setPage(page + 1)}>
          Older →
        </button>
      </div>
    </div>
  );
}
