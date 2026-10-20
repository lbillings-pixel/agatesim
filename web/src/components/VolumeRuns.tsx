import type { VolumeRunSummary } from "../api";
import { volume as volumeApi } from "../api";
import { DeleteRun, RunsUsage } from "./RunHousekeeping";

function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Share of random cuts that pass, as "68% of 40 cuts"; null when no survey was saved. */
export function surveyLabel(survey: VolumeRunSummary["survey"]): string | null {
  if (!survey || survey.pass_rate === null) return null;
  return `${Math.round(survey.pass_rate * 100)}% of ${survey.cuts} cuts`;
}

interface Props {
  runs: VolumeRunSummary[];
  opening: string | null;
  onOpen: (id: string) => void;
  onDeleted: (id: string) => void;
}

/** Saved full 3D runs, newest first; opening one loads its settings into the 3D screen. */
export function VolumeRuns({ runs, opening, onOpen, onDeleted }: Props) {
  return (
    <section className="volume-runs" aria-labelledby="volume-runs-title">
      <h2 id="volume-runs-title">Saved 3D runs</h2>
      <RunsUsage refresh={runs} />
      {runs.length === 0 ? (
        <p className="muted small">
          Runs you save with “Save a full 3D run” appear here, each with its configured cut and,
          if it names a form, how often random cuts show it.
        </p>
      ) : (
        <ul>
          {runs.map((r) => {
            const rate = surveyLabel(r.survey);
            return (
              <li key={r.id}>
                <button
                  type="button"
                  className="run-item"
                  onClick={() => onOpen(r.id)}
                  disabled={opening !== null}
                  title="Open this run's settings in the 3D screen"
                >
                  <img src={volumeApi.slabUrl(r.id)} alt="" loading="lazy" />
                  <span className="run-text">
                    <strong>{r.name}</strong>
                    <span className="muted small">
                      {r.solid} · {r.model} · {r.grid.nx}³
                    </span>
                    <span className="muted small">
                      {when(r.started_utc)}
                      {rate ? ` · random cuts pass ${rate}` : ""}
                    </span>
                  </span>
                  {opening === r.id ? (
                    <span className="pill">opening…</span>
                  ) : (
                    r.passed !== null && (
                      <span className={`pill ${r.passed ? "pass" : "fail"}`}>{r.passed ? "pass" : "fail"}</span>
                    )
                  )}
                </button>
                <DeleteRun id={r.id} name={r.name} onDeleted={onDeleted} />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
