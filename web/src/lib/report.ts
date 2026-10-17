// A run report: one self-contained HTML page with the slab, its tests, its band
// statistics and every setting, for keeping or sharing outside the app.

import type { ArchetypeInfo, BandStats, Evaluation, ModelInfo, RunConfig } from "../api";
import { STATS_ROWS } from "../components/StatsPanel";
import { overallVerdict } from "../components/CriteriaPanel";
import { flatten } from "./diff";
import { labelFor } from "./schema";

export interface ReportInput {
  config: RunConfig;
  /** The slab as a data: URL, so the page needs nothing else. */
  image: string;
  evaluation: Evaluation | null;
  stats: BandStats | null;
  archetypes: ArchetypeInfo[];
  models: ModelInfo[];
  /** The preset's description, when the run is a preset. */
  description?: string;
  /** Where the run came from: a saved run's id and size, or "preview". */
  source: string;
  /** The code version, when known. */
  commit?: string | null;
  created: Date;
}

const ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ESCAPES[c] ?? c);
}

function rows(cells: string[][]): string {
  return cells.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("\n");
}

export function buildReport(input: ReportInput): string {
  const { config, evaluation, stats } = input;
  const model = input.models.find((m) => m.kind === config.model.kind);
  const archetype = input.archetypes.find((a) => a.id === evaluation?.archetype);
  const verdict = evaluation ? overallVerdict(evaluation) : null;
  const tests = evaluation
    ? rows(
        evaluation.criteria.map((r) => [
          `<code>${escapeHtml(r.id)}</code>`,
          r.value === null ? "not judged" : escapeHtml(String(Number(r.value.toPrecision(4)))),
          escapeHtml(archetype?.criteria.find((c) => c.id === r.id)?.pass ?? ""),
          r.value === null ? "not judged" : r.passed ? "pass" : "fail",
        ]),
      )
    : "";
  const measures = stats
    ? rows(
        STATS_ROWS.flatMap((row) => {
          const v = row.value(stats);
          return v === null ? [] : [[escapeHtml(row.label), escapeHtml(row.format(v))]];
        }),
      )
    : "";
  const settings = rows(
    Object.entries(flatten(config))
      .filter(([path]) => path !== "name")
      .map(([path, v]) => [escapeHtml(path.split("/").map(labelFor).join(" › ")), `<code>${escapeHtml(v)}</code>`]),
  );
  const title = `agatesim run: ${config.name}`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
  :root { color-scheme: light dark; --fg: #1c2328; --muted: #5d6870; --line: #d4d9dc; --bg: #fff; --pass: #2c7a4c; --fail: #b03a2a; }
  @media (prefers-color-scheme: dark) { :root { --fg: #e4e8eb; --muted: #9aa6b0; --line: #2e3842; --bg: #14191e; --pass: #6cc792; --fail: #ef8a78; } }
  body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, sans-serif; }
  main { max-width: 56rem; margin: 0 auto; padding: 1.5rem 16px 3rem; display: grid; gap: 1.25rem; }
  h1 { font-size: 1.5rem; margin: 0; } h2 { font-size: 1.1rem; margin: 0 0 0.4rem; }
  p { margin: 0; } .muted { color: var(--muted); }
  img { max-width: 100%; height: auto; display: block; background: #111; border-radius: 4px; }
  table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
  td, th { text-align: left; padding: 0.3rem 0.6rem 0.3rem 0; border-top: 1px solid var(--line); vertical-align: top; }
  code { font-family: ui-monospace, Consolas, monospace; font-size: 0.85rem; word-break: break-all; }
  .verdict { font-weight: 600; } .pass { color: var(--pass); } .fail { color: var(--fail); }
</style>
</head>
<body>
<main>
  <header>
    <h1>${escapeHtml(config.name)}</h1>
    <p class="muted">${escapeHtml(model?.title ?? config.model.kind)} · ${escapeHtml(input.source)} · seed ${config.seed} · made ${escapeHtml(input.created.toISOString().slice(0, 16).replace("T", " "))} UTC${input.commit ? ` · code ${escapeHtml(input.commit.slice(0, 7))}` : ""}</p>
  </header>
  ${input.description ? `<p>${escapeHtml(input.description)}</p>` : ""}
  <img src="${escapeHtml(input.image)}" alt="Rendered slab of ${escapeHtml(config.name)}">
  ${
    evaluation
      ? `<section><h2>Tests: ${escapeHtml(archetype?.name ?? evaluation.archetype)}</h2>
  <p class="verdict ${verdict?.tone ?? ""}">${escapeHtml(verdict?.label ?? "")}</p>
  <table><thead><tr><th>Test</th><th>Value</th><th>Pass if</th><th>Result</th></tr></thead><tbody>
${tests}
  </tbody></table></section>`
      : `<p class="muted">Not judged as any form.</p>`
  }
  ${stats ? `<section><h2>Band statistics</h2><table><tbody>\n${measures}\n</tbody></table></section>` : ""}
  <section><h2>Settings</h2><table><tbody>
${settings}
  </tbody></table></section>
  <p class="muted">Passing a form's tests with a procedural model shows the simulator can represent the form; with a mechanistic model, that the mechanism can make it, not that nature does.</p>
</main>
</body>
</html>
`;
}
