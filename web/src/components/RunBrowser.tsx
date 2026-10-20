import type { Job, RunSummary } from "../api";
import { api, progress } from "../api";
import { DeleteRun, RunsUsage } from "./RunHousekeeping";
import { TaskProgress } from "./TaskProgress";

function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

interface Props {
  runs: RunSummary[];
  jobs: Job[];
  selected: string | null;
  pinned: string | null;
  onSelect: (id: string) => void;
  onDeleted: (id: string) => void;
}

export function RunBrowser({ runs, jobs, selected, pinned, onSelect, onDeleted }: Props) {
  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
  const failed = jobs.filter((j) => j.status === "failed");
  return (
    <aside className="runs" aria-labelledby="runs-title">
      <h2 id="runs-title">Runs</h2>
      <RunsUsage refresh={runs} />
      {active.map((j) => (
        <div key={j.id} className="job">
          <span>
            <span className="spinner" aria-hidden="true" />
            {j.name} · {j.status === "queued" ? "waiting" : "running"}
          </span>
          <TaskProgress
            task={j.status === "running" ? j.id : null}
            title="Full run"
            onCancel={() => void progress.cancel(j.id)}
          />
        </div>
      ))}
      {failed.map((j) => (
        <div key={j.id} className={`job${j.error === "cancelled" ? "" : " failed"}`} role="alert">
          {j.error === "cancelled" ? `${j.name} cancelled` : `${j.name} failed: ${j.error ?? ""}`}
        </div>
      ))}
      {runs.length === 0 && active.length === 0 && (
        <p className="muted small">
          Full-resolution runs appear here. Press “Run full resolution” to make one; each run
          is saved with its exact settings so it can be reproduced.
        </p>
      )}
      <ul>
        {runs.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              className={`run-item${r.id === selected ? " selected" : ""}`}
              onClick={() => onSelect(r.id)}
            >
              <img src={api.slabUrl(r.id)} alt="" loading="lazy" />
              <span className="run-text">
                <strong>{r.name}</strong>
                <span className="muted small">
                  {r.cavity} · {r.nx}×{r.ny}
                </span>
                <span className="muted small">{when(r.started_utc)}</span>
              </span>
              {r.passed !== null && (
                <span className={`pill ${r.passed ? "pass" : "fail"}`}>{r.passed ? "pass" : "fail"}</span>
              )}
              {r.id === pinned && <span className="pill pinned">pinned</span>}
            </button>
            <DeleteRun id={r.id} name={r.name} onDeleted={onDeleted} />
          </li>
        ))}
      </ul>
    </aside>
  );
}
