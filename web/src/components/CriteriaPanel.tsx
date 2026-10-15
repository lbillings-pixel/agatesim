import type { ArchetypeInfo, Evaluation } from "../api";

function formatNumber(value: number): string {
  if (value === 0) return "0";
  const abs = Math.abs(value);
  return abs >= 100 ? value.toFixed(0) : abs >= 0.01 ? value.toPrecision(3) : value.toExponential(1);
}

/** A test that couldn't be measured isn't a failure of the form; say so. */
export function overallVerdict(evaluation: Evaluation): { label: string; tone: "pass" | "fail" | "na" } {
  if (evaluation.passed) return { label: "all tests pass", tone: "pass" };
  const failed = evaluation.criteria.some((r) => r.value !== null && !r.passed);
  if (failed) return { label: "fails", tone: "fail" };
  return { label: "partly judged", tone: "na" };
}

interface Props {
  evaluation: Evaluation | null;
  archetypes: ArchetypeInfo[];
}

export function CriteriaPanel({ evaluation, archetypes }: Props) {
  if (!evaluation) {
    return (
      <section className="criteria-panel">
        <h3>Archetype tests</h3>
        <p className="muted">Choose a form under “Judge as” to test this result against it.</p>
      </section>
    );
  }
  const info = archetypes.find((a) => a.id === evaluation.archetype);
  const verdict = overallVerdict(evaluation);
  return (
    <section className="criteria-panel">
      <div className="criteria-head">
        <h3>{info?.name ?? evaluation.archetype}</h3>
        <span className={`pill ${verdict.tone}`}>{verdict.label}</span>
      </div>
      <table>
        <thead>
          <tr>
            <th scope="col">Test</th>
            <th scope="col">Value</th>
            <th scope="col">Pass if</th>
            <th scope="col">
              <span className="visually-hidden">Result</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {evaluation.criteria.map((r) => {
            const c = info?.criteria.find((x) => x.id === r.id);
            return (
              <tr key={r.id} title={r.detail}>
                <td>
                  <code>{r.id}</code>
                  {c && <div className="muted small">{c.description}</div>}
                </td>
                <td className="num">{r.value === null ? "n/a" : formatNumber(r.value)}</td>
                <td className="num">{c?.pass ?? ""}</td>
                <td>
                  <span className={`dot ${r.value === null ? "na" : r.passed ? "pass" : "fail"}`}>
                    {r.value === null ? "not judged" : r.passed ? "pass" : "fail"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {evaluation.criteria.some((r) => r.value === null) && (
        <p className="muted small">
          “Not judged” means the result can’t be measured at this resolution or in this
          cavity. Full-resolution runs judge every test.
        </p>
      )}
    </section>
  );
}
