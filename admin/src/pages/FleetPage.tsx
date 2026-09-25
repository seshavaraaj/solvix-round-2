import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { FleetConfig } from "../api/types";
import { validateFleet } from "../lib/validate";

export function FleetPage() {
  const q = useQuery({ queryKey: ["fleet"], queryFn: api.getFleet });
  return (
    <div className="page">
      <h2>Fleet by depot</h2>
      {q.isPending && <p className="muted">Loading fleet…</p>}
      {q.isError && <p className="error">Could not load fleet: {(q.error as Error).message}</p>}
      {q.data?.length === 0 && <p className="muted">No depots configured.</p>}
      <div className="cards">
        {q.data?.map((f) => <DepotForm key={f.depot_id} depot={f} />)}
      </div>
    </div>
  );
}

const FIELDS: { key: "fleet_size" | "reserve" | "out_of_service"; label: string }[] = [
  { key: "fleet_size", label: "Fleet size" },
  { key: "reserve", label: "Reserve" },
  { key: "out_of_service", label: "Out of service" },
];

function DepotForm({ depot }: { depot: FleetConfig }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(depot);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const invalid = validateFleet(draft);
  const dirty = FIELDS.some((f) => draft[f.key] !== depot[f.key]);

  const save = useMutation({
    mutationFn: api.putFleet,
    onSuccess: (saved) => {
      setDraft(saved);
      setMsg({ ok: true, text: "Saved." });
      qc.invalidateQueries({ queryKey: ["fleet"] });
    },
    onError: (err) => setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Save failed" }),
  });

  return (
    <form
      className="card form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!invalid) save.mutate(draft);
      }}
    >
      <h3>{depot.name}</h3>
      <p className="muted small">{depot.depot_id}</p>
      {FIELDS.map((f) => (
        <label key={f.key}>
          {f.label}
          <input
            type="number"
            min={0}
            step={1}
            value={draft[f.key]}
            onChange={(e) => {
              setMsg(null);
              setDraft({ ...draft, [f.key]: Number(e.target.value) });
            }}
          />
        </label>
      ))}
      <p className="muted small">In service: {Math.max(0, draft.fleet_size - draft.reserve - draft.out_of_service)} buses</p>
      {invalid && <p className="error">{invalid}</p>}
      {msg && <p className={msg.ok ? "ok" : "error"}>{msg.text}</p>}
      <div className="row end">
        <button type="submit" className="primary" disabled={!!invalid || !dirty || save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}
