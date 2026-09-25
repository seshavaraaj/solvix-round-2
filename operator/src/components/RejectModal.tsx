import { useState, type FormEvent } from "react";
import { REJECT_REASONS, type RejectReason } from "../api/types";
import { humanize } from "../lib/format";

interface Props {
  onSubmit: (reason: RejectReason, note: string) => void;
  onCancel: () => void;
  busy?: boolean;
}

export function isRejectReason(x: string): x is RejectReason {
  return (REJECT_REASONS as string[]).includes(x);
}

export function RejectModal({ onSubmit, onCancel, busy }: Props) {
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!isRejectReason(reason)) {
      setError("Choose a reason.");
      return;
    }
    onSubmit(reason, note.trim());
  }

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <form className="modal card" onSubmit={submit} onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Reject recommendation">
        <h3>Reject recommendation</h3>
        <label>
          Reason (required)
          <select value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason">
            <option value="">Choose…</option>
            {REJECT_REASONS.map((r) => (
              <option key={r} value={r}>
                {humanize(r)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Note (optional)
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
        </label>
        {error && <p className="error">{error}</p>}
        <div className="row end">
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="danger" disabled={busy}>
            Reject
          </button>
        </div>
      </form>
    </div>
  );
}
