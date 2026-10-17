import { settingDiffs } from "../lib/diff";

interface Props {
  a: { title: string; config: object };
  b: { title: string; config: object };
}

/** The settings that differ between two runs, side by side. */
export function RunDiff({ a, b }: Props) {
  const diffs = settingDiffs(a.config, b.config);
  return (
    <section className="run-diff" aria-labelledby="run-diff-title">
      <h3 id="run-diff-title">What differs</h3>
      {diffs.some((d) => d.path === "model/kind") && (
        <p className="muted small">The runs use different models, so their model settings aren’t compared one by one.</p>
      )}
      {diffs.length === 0 ? (
        <p className="muted small">The two runs have the same settings.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Setting</th>
                <th scope="col">{a.title}</th>
                <th scope="col">{b.title}</th>
              </tr>
            </thead>
            <tbody>
              {diffs.map((d) => (
                <tr key={d.path}>
                  <td>{d.label}</td>
                  <td className="num">{d.a ?? "—"}</td>
                  <td className="num">{d.b ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
