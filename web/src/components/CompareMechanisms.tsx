import { useEffect, useRef, useState } from "react";
import { api, type ModelInfo, type PreviewResult, type RunConfig } from "../api";
import { defaultsFor } from "../lib/schema";

/** The mechanisms compared, in order: one that builds fortification in by design, and the two
 * mechanistic models whose corners differ (ADR 0015, ADR 0026). */
export const MECHANISMS = [
  { kind: "procedural-fortification", label: "Procedural", note: "bands laid at set distances from the wall" },
  { kind: "mechanistic-front-feedback", label: "H1 front feedback", note: "bands from feedback at the growth front" },
  { kind: "mechanistic-liesegang", label: "H2 Liesegang", note: "rings from diffusing chemicals" },
] as const;

/** Mechanisms only practical on the GPU: on the CPU they take many minutes. */
export const NEEDS_GPU = new Set<string>(["mechanistic-liesegang"]);

/** The current cavity with each compared mechanism at its default settings, judged as
 * fortification. Mechanisms that need the GPU are left out when the server has none. */
export function comparisonConfigs(config: RunConfig, models: ModelInfo[], gpu = true): RunConfig[] {
  return MECHANISMS.flatMap(({ kind }) => {
    if (!gpu && NEEDS_GPU.has(kind)) return [];
    const info = models.find((m) => m.kind === kind);
    if (!info) return [];
    const schedules = Object.fromEntries(info.schedules.map((v) => [v.key, v.default]));
    return [
      {
        ...config,
        name: `compare-${kind}`,
        archetype: "fortification",
        model: {
          kind,
          ...defaultsFor(info.schema.properties),
          ...(info.schedules.length > 0 ? { schedules } : {}),
        },
      },
    ];
  });
}

function criterion(result: PreviewResult, id: string): string {
  const c = result.evaluation?.criteria.find((x) => x.id === id);
  return c?.value == null ? "can’t judge" : c.value.toFixed(2);
}

/** Why a criterion couldn't be judged (for example, bands too close at this size), if it couldn't. */
function unjudged(result: PreviewResult, id: string): string | null {
  const c = result.evaluation?.criteria.find((x) => x.id === id);
  return c && c.value === null ? c.detail : null;
}

interface Props {
  config: RunConfig;
  models: ModelInfo[];
  resolution: number;
  gpu: boolean;
}

/** The current cavity filled by each mechanism in turn, side by side, with the fortification
 * tests' verdict and the two numbers that tell them apart: corners and closed rings. */
export function CompareMechanisms({ config, models, resolution, gpu }: Props) {
  const [results, setResults] = useState<Record<string, PreviewResult | string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const cavityKey = JSON.stringify(config.cavity);
  const [shownFor, setShownFor] = useState<string | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const run = async () => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setResults({});
    setShownFor(cavityKey);
    for (const c of comparisonConfigs(config, models, gpu)) {
      setBusy(c.model.kind);
      try {
        const r = await api.preview(c, resolution, controller.signal);
        setResults((prev) => ({ ...prev, [c.model.kind]: r }));
      } catch (e) {
        if (controller.signal.aborted) return;
        setResults((prev) => ({ ...prev, [c.model.kind]: e instanceof Error ? e.message : String(e) }));
      }
    }
    setBusy(null);
  };

  const current = shownFor === cavityKey;
  return (
    <section className="mechanisms" aria-labelledby="mechanisms-title">
      <div className="mechanisms-head">
        <h2 id="mechanisms-title">Compare mechanisms</h2>
        <button type="button" onClick={() => void run()} disabled={busy !== null}>
          {busy ? "Comparing…" : current ? "Compare again" : "Compare on this cavity"}
        </button>
      </div>
      <p className="muted small">
        The same cavity filled by each mechanism, judged as fortification. Corners: how far a band
        travels sideways while turning a corner, in band spacings (sharp is low; the test asks for
        0.7 or less). Real agates measure 0.03–0.63. Runs at {resolution} px; bands finer than that can’t be judged here.
      </p>
      {current && (
        <div className="mechanisms-grid">
          {MECHANISMS.map(({ kind, label, note }) => {
            const r = results[kind];
            return (
              <figure key={kind}>
                {typeof r === "object" ? (
                  <img src={r.image} alt={`Slab filled by ${label}`} />
                ) : (
                  <div className="mechanisms-placeholder muted small">
                    {typeof r === "string"
                      ? r
                      : !gpu && NEEDS_GPU.has(kind)
                        ? "Needs the GPU: start the app with AGATESIM_GPU=1"
                        : busy === kind
                          ? "Working…"
                          : "Waiting"}
                  </div>
                )}
                <figcaption>
                  <strong>{label}</strong>
                  <span className="muted small">{note}</span>
                  {typeof r === "object" && r.evaluation && (
                    <span className="small">
                      <span className={`pill ${r.evaluation.passed ? "pass" : "fail"}`}>
                        {r.evaluation.passed ? "pass" : "fail"}
                      </span>{" "}
                      corners {criterion(r, "corners-preserved")} · closed rings{" "}
                      {criterion(r, "closed-bands")}
                    </span>
                  )}
                  {typeof r === "object" && unjudged(r, "corners-preserved") && (
                    <span className="muted small">Corners: {unjudged(r, "corners-preserved")}</span>
                  )}
                </figcaption>
              </figure>
            );
          })}
        </div>
      )}
    </section>
  );
}
