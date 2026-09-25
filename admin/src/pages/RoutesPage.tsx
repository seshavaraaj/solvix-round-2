import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { Route } from "../api/types";
import { validateRoute } from "../lib/validate";

export function RoutesPage() {
  const q = useQuery({ queryKey: ["admin-routes"], queryFn: api.getAdminRoutes });
  const [editing, setEditing] = useState<Route | null>(null);

  return (
    <div className="page">
      <h2>Routes</h2>
      {q.isPending && <p className="muted">Loading routes…</p>}
      {q.isError && <p className="error">Could not load routes: {(q.error as Error).message}</p>}
      {q.data?.length === 0 && <p className="muted">No routes configured.</p>}
      {q.data && q.data.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Depot</th>
              <th className="num">Min headway</th>
              <th className="num">Stops</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {q.data.map((r) => (
              <tr key={r.id}>
                <td>
                  <span className="swatch" style={{ background: r.color }} />
                  {r.id}
                </td>
                <td>{r.name}</td>
                <td>{r.depot_id}</td>
                <td className="num">{r.min_headway_min} min</td>
                <td className="num">{r.stops.length}</td>
                <td>
                  <button type="button" onClick={() => setEditing(r)}>
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing && <RouteForm key={editing.id} route={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function RouteForm({ route, onClose }: { route: Route; onClose: () => void }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Route>(route);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: api.putAdminRoute,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-routes"] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Save failed"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const msg = validateRoute(draft);
    setError(msg);
    if (!msg) save.mutate(draft);
  }

  const set = <K extends keyof Route>(k: K, v: Route[K]) => setDraft({ ...draft, [k]: v });

  return (
    <form className="card form" onSubmit={submit} aria-label={`Edit route ${route.id}`}>
      <h3>Edit route {route.id}</h3>
      <div className="grid2">
        <label>
          Name
          <input value={draft.name} onChange={(e) => set("name", e.target.value)} />
        </label>
        <label>
          Depot ID
          <input value={draft.depot_id} onChange={(e) => set("depot_id", e.target.value)} />
        </label>
        <label>
          Minimum headway (min)
          <input
            type="number"
            min={1}
            value={draft.min_headway_min}
            onChange={(e) => set("min_headway_min", Number(e.target.value))}
          />
        </label>
        <label>
          Colour
          <span className="row">
            <input type="color" value={draft.color.toLowerCase()}onChange={(e) => set("color", e.target.value.toUpperCase())} />
            <input value={draft.color} onChange={(e) => set("color", e.target.value)} />
          </span>
        </label>
      </div>
      <h4>Stops (from GTFS, read-only)</h4>
      <ol className="stops">
        {[...draft.stops]
          .sort((a, b) => a.seq - b.seq)
          .map((s) => (
            <li key={s.id}>
              {s.name} <span className="muted">({s.id})</span>
            </li>
          ))}
      </ol>
      {error && <p className="error">{error}</p>}
      <div className="row end">
        <button type="button" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}
