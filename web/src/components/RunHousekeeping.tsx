import { useEffect, useState } from "react";

import { api } from "../api";
import { formatBytes } from "../lib/bytes";

/** Delete a saved run, after an inline "are you sure" (no browser dialog). */
export function DeleteRun({ id, name, onDeleted }: { id: string; name: string; onDeleted: (id: string) => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!asking) {
    return (
      <button type="button" className="link-button run-delete small" onClick={() => setAsking(true)} title={`Delete ${name}`}>
        Delete
      </button>
    );
  }
  const remove = () => {
    setBusy(true);
    api.deleteRun(id).then(
      () => onDeleted(id),
      (e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
        setBusy(false);
      },
    );
  };
  return (
    <span className="run-delete small" role="group" aria-label={`Delete ${name}?`}>
      {error ? <span className="error">{error}</span> : <span>Delete this run?</span>}
      <button type="button" className="link-button" onClick={remove} disabled={busy}>
        {busy ? "Deleting…" : "Yes"}
      </button>
      <button type="button" className="link-button" onClick={() => setAsking(false)} disabled={busy}>
        No
      </button>
    </span>
  );
}

/** How many runs are saved and the space they take (2D and 3D share a folder). */
export function RunsUsage({ refresh }: { refresh: unknown }) {
  const [usage, setUsage] = useState<{ runs: number; bytes: number } | null>(null);
  useEffect(() => {
    api.runsUsage().then(setUsage, () => undefined);
  }, [refresh]);
  if (!usage || usage.runs === 0) return null;
  return (
    <p className="muted small runs-usage">
      {usage.runs} saved {usage.runs === 1 ? "run" : "runs"} (2D and 3D) · {formatBytes(usage.bytes)} on disk
    </p>
  );
}
