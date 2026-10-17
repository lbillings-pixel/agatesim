import { useEffect, useMemo, useRef, useState } from "react";
import { api, type ArchetypeInfo, type Meta, type PreviewResult, type RunConfig } from "../api";
import { overallVerdict } from "./CriteriaPanel";
import { fieldsFor, imposedSettings } from "../lib/schema";

type Preset = Meta["presets"][number];

export interface FormPair {
  archetype: ArchetypeInfo;
  procedural: Preset | null;
  mechanistic: Preset | null;
}

/** Each form with its verification presets: `<id>` for the procedural tier and
 * `<id>-mechanistic` for the mechanistic tier (the naming the tests enforce). */
export function formPairs(meta: Pick<Meta, "presets" | "archetypes">): FormPair[] {
  const byName = new Map(meta.presets.map((p) => [p.name, p]));
  return meta.archetypes
    .filter((a) => a.implemented)
    .map((a) => ({
      archetype: a,
      procedural: byName.get(a.id) ?? null,
      mechanistic: byName.get(`${a.id}-mechanistic`) ?? null,
    }));
}

/** Why a form has no mechanistic version yet (ADR 0035). */
const PENDING: Record<string, string> = {
  shadow:
    "The banding mechanism's clear and milky bands don't contrast enough, and no source yet links how fast a band grows to how milky it is (ADR 0041).",
};

const TIERS = [
  {
    key: "procedural",
    title: "Rule-based",
    note: "The form is built in by design: the model sets properties of the result directly.",
  },
  {
    key: "mechanistic",
    title: "From a mechanism",
    note: "The form emerges from a proposed formation process; only conditions are set by hand.",
  },
] as const;

interface Props {
  meta: Meta;
  resolution: number;
  onOpen: (config: RunConfig) => void;
}

/** Each form made two ways, side by side: by the procedural model that builds it in, and
 * by a mechanistic model where it emerges, with each one's test results and the settings
 * that fix the result directly. */
export function TwoWays({ meta, resolution, onOpen }: Props) {
  const pairs = useMemo(() => formPairs(meta), [meta]);
  const [selected, setSelected] = useState<string>(
    () => pairs.find((p) => p.mechanistic)?.archetype.id ?? pairs[0]?.archetype.id ?? "",
  );
  const [results, setResults] = useState<Record<string, PreviewResult | string>>({});
  const abort = useRef<AbortController | null>(null);
  const pair = pairs.find((p) => p.archetype.id === selected);

  useEffect(() => {
    if (!pair) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    void (async () => {
      for (const preset of [pair.procedural, pair.mechanistic]) {
        if (!preset || results[preset.name]) continue;
        try {
          const r = await api.preview(preset.config, resolution, controller.signal);
          setResults((prev) => ({ ...prev, [preset.name]: r }));
        } catch (e) {
          if (controller.signal.aborted) return;
          setResults((prev) => ({ ...prev, [preset.name]: e instanceof Error ? e.message : String(e) }));
        }
      }
    })();
    return () => controller.abort();
    // Results are cached by preset name; re-run only when the form or size changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pair, resolution]);

  if (!pair) return <p className="muted">No forms to show.</p>;
  const verified = pairs.filter((p) => p.mechanistic).length;

  return (
    <div className="twoways">
      <nav className="twoways-forms" aria-label="Forms">
        <p className="muted small">
          {verified} of {pairs.length} forms are made both ways.
        </p>
        <div role="radiogroup" aria-label="Form">
          {pairs.map((p) => (
            <button
              key={p.archetype.id}
              type="button"
              role="radio"
              aria-checked={p.archetype.id === selected}
              onClick={() => setSelected(p.archetype.id)}
            >
              <span>{p.archetype.name}</span>
              <span className={`pill ${p.mechanistic ? "pass" : "na"}`}>{p.mechanistic ? "both" : "rule-based only"}</span>
            </button>
          ))}
        </div>
      </nav>

      <section className="twoways-main" aria-labelledby="twoways-title">
        <h2 id="twoways-title">{pair.archetype.name}</h2>
        <p className="muted small">
          The same tests judge both versions. Passing with the rule-based model shows the simulator can
          represent and measure the form; passing with a mechanism shows that mechanism <em>can</em> make
          it, not that nature does. Previews at {resolution} px; the verification runs at 768 px.
        </p>
        <div className="twoways-grid">
          {TIERS.map((tier) => {
            const preset = pair[tier.key];
            return (
              <article key={tier.key} className="twoways-card">
                <header>
                  <h3>{tier.title}</h3>
                  <p className="muted small">{tier.note}</p>
                </header>
                {preset ? (
                  <Version preset={preset} result={results[preset.name]} meta={meta} onOpen={onOpen} />
                ) : (
                  <p className="twoways-pending">
                    <strong>Not yet.</strong> {PENDING[pair.archetype.id] ?? "No mechanistic version yet."}
                  </p>
                )}
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}

interface VersionProps {
  preset: Preset;
  result: PreviewResult | string | undefined;
  meta: Meta;
  onOpen: (config: RunConfig) => void;
}

function Version({ preset, result, meta, onOpen }: VersionProps) {
  const model = meta.models.find((m) => m.kind === preset.config.model.kind);
  const imposed = model ? imposedSettings(fieldsFor(model.schema), preset.config.model) : [];
  // Only the conditions this preset changes from their defaults.
  const schedules = (model?.schedules ?? [])
    .filter((v) => {
      const s = preset.config.model.schedules?.[v.key];
      return s !== undefined && (s.base !== v.default.base || JSON.stringify(s.events) !== JSON.stringify(v.default.events));
    })
    .map((v) => v.label.toLowerCase());
  const criteria = meta.archetypes.find((a) => a.id === preset.config.archetype)?.criteria ?? [];
  const evaluation = typeof result === "object" ? result.evaluation : null;
  return (
    <>
      <figure className="twoways-slab">
        {typeof result === "object" ? (
          <img src={result.image} alt={`Slab from the ${preset.name} preset`} />
        ) : (
          <div className="mechanisms-placeholder muted small">{result ?? "Working…"}</div>
        )}
        <figcaption className="small">
          <code>{preset.name}</code> · {model?.title ?? preset.config.model.kind}
        </figcaption>
      </figure>
      {evaluation && (
        <table className="twoways-tests">
          <caption className="small">
            <span className={`pill ${overallVerdict(evaluation).tone}`}>{overallVerdict(evaluation).label}</span>
          </caption>
          <thead>
            <tr>
              <th scope="col">Test</th>
              <th scope="col">Value</th>
              <th scope="col">Pass if</th>
            </tr>
          </thead>
          <tbody>
            {evaluation.criteria.map((c) => (
              <tr key={c.id}>
                <td>
                  <code>{c.id}</code>
                </td>
                <td className={c.passed ? "pass" : c.value === null ? "muted" : "fail"} title={c.value === null ? c.detail : undefined}>
                  {c.value === null ? "can’t judge here" : c.value.toFixed(3)}
                </td>
                <td className="muted">{criteria.find((x) => x.id === c.id)?.pass ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="small">
        <strong>Set directly:</strong>{" "}
        {imposed.length === 0 ? (
          <span>nothing about the result.</span>
        ) : (
          <ul className="twoways-imposed">
            {imposed.map((s) => (
              <li key={s.label}>
                {s.label}: {s.value}
                {s.units && ` ${s.units}`}
              </li>
            ))}
          </ul>
        )}
        {schedules.length > 0 && (
          <p className="muted">Conditions scheduled over time: {schedules.join(", ")}.</p>
        )}
      </div>
      {preset.description && <p className="small">{preset.description}</p>}
      <button type="button" onClick={() => onOpen(preset.config)}>
        Open in the simulator
      </button>
    </>
  );
}
