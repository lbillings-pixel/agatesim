import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  progress as progressApi,
  type Job,
  type Meta,
  type PreviewResult,
  type RandomizeExtra,
  type RunConfig,
  type RunDetail,
  type RunSummary,
  type Tube,
} from "./api";
import { CavityDrawer, type Drawn } from "./components/CavityDrawer";
import { CavityMenu } from "./components/CavityMenu";
import { CriteriaPanel } from "./components/CriteriaPanel";
import { ParamPanel, Slider } from "./components/ParamPanel";
import { TwoWays } from "./components/TwoWays";
import { RunBrowser } from "./components/RunBrowser";
import { ScheduleEditor } from "./components/ScheduleEditor";
import { SlabView } from "./components/SlabView";
import { SpecimenWorkbench } from "./components/SpecimenWorkbench";
import { StatsPanel } from "./components/StatsPanel";
import { TubePanel } from "./components/TubePanel";
import { VolumeWorkbench } from "./components/VolumeWorkbench";
import { type Control, defaultsFor, fieldsFor, withSetting } from "./lib/schema";
import { newTaskId } from "./lib/progress";
import { TaskProgress } from "./components/TaskProgress";
import { formPresets, otherPresets, tierOf } from "./lib/forms";
import { GrowthControls } from "./components/GrowthControls";
import { RunDiff } from "./components/RunDiff";
import { Glossary } from "./components/Glossary";
import { Tour } from "./components/Tour";
import { saveBlob } from "./lib/animation";
import { buildReport } from "./lib/report";

const PREVIEW_RESOLUTIONS = [128, 192, 256, 384];
const RUN_RESOLUTIONS = [512, 768, 1024, 1536, 2048];
const DEBOUNCE_MS = 250;

const SIZE_CONTROL: Control = {
  key: "size_mm", label: "Cavity size", units: "mm", nature: "physical",
  description: "Longest dimension of the cavity.", min: 10, max: 150, step: 1, defaultValue: 50,
};
const ROTATION_CONTROL: Control = {
  key: "rotation_deg", label: "Rotation", units: "deg", nature: "physical",
  description: "Rotates the cavity in the slab plane.", min: 0, max: 359, step: 1, defaultValue: 0,
};

/** The archetype a model is most naturally judged as, given the cavity's host. */
function suggestedArchetype(kind: string, host: string | undefined): string | null {
  if (kind === "procedural-waterline") return "waterline";
  if (kind === "procedural-fortification") return host === "seam" ? "seam" : "fortification";
  return null;
}

/** Automatic run name, used until the user types their own. */
function autoName(config: RunConfig): string {
  return `${config.model.kind.replace(/^procedural-/, "")}-${cavityLabel(config)}`;
}

function cavityLabel(config: RunConfig): string {
  return config.cavity.preset ?? "drawn";
}

function drawnOf(config: RunConfig): Drawn | null {
  const { outline, host, smooth } = config.cavity;
  return outline && host ? { outline, host, smooth: smooth ?? false } : null;
}

const round2 = (v: number) => Math.round(v * 100) / 100;

/** How far Randomize moves the key settings toward random values in their ranges. */
const STRENGTHS = [
  [0.2, "Subtle"],
  [0.4, "Medium"],
  [0.7, "Bold"],
  [1, "Wild"],
] as const;
const HISTORY_LIMIT = 50;
const COALESCE_MS = 700; // changes closer together than this (a slider drag) undo as one

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [config, setConfig] = useState<RunConfig | null>(null);
  const [previewRes, setPreviewRes] = useState(256);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewTask, setPreviewTask] = useState<string | null>(null);
  const [previewAgain, setPreviewAgain] = useState(0);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [runResolution, setRunResolution] = useState(768);
  const [selected, setSelected] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  // Comparing with a pinned run: one growth slider can drive both slabs.
  const [linkGrowth, setLinkGrowth] = useState(true);
  const [sharedGrowth, setSharedGrowth] = useState(1);
  const [details, setDetails] = useState<Record<string, RunDetail>>({});
  const [drawer, setDrawer] = useState<"edit" | "new" | null>(null);
  const [lastDrawn, setLastDrawn] = useState<Drawn | null>(null);
  const [placingTubes, setPlacingTubes] = useState(false);
  const [tubeRadius, setTubeRadius] = useState(0.3);
  const [screen, setScreen] = useState<"simulator" | "twoways" | "volume" | "specimens">("simulator");
  const [light, setLight] = useState<"reflected" | "shadow" | "iris">("reflected");
  const [lightAngle, setLightAngle] = useState(30);
  // Direction of the tilt in the slab plane: diffraction from a band runs across it,
  // so horizontal bands colour only when the view tilts up or down. 45° catches both.
  const [lightDirection, setLightDirection] = useState(45);
  const [opticsImage, setOpticsImage] = useState<string | null>(null);
  const [opticsNote, setOpticsNote] = useState("");
  // Undo and redo: earlier and later settings, recorded whenever the settings change.
  const [past, setPast] = useState<RunConfig[]>([]);
  const [future, setFuture] = useState<RunConfig[]>([]);
  const previous = useRef<RunConfig | null>(null);
  const travelling = useRef(false);
  const lastRecorded = useRef(0);
  const [strength, setStrength] = useState(0.4);
  const [keepForm, setKeepForm] = useState(false);
  const [extras, setExtras] = useState<RandomizeExtra[]>([]);
  const [randomTask, setRandomTask] = useState<string | null>(null);
  const randomAbort = useRef<AbortController | null>(null);
  const randomizing = randomTask !== null;
  const [randomNote, setRandomNote] = useState("");

  useEffect(() => {
    const before = previous.current;
    previous.current = config;
    if (!before || !config || before === config) return;
    if (travelling.current) {
      travelling.current = false;
      return;
    }
    const now = Date.now();
    if (now - lastRecorded.current > COALESCE_MS) setPast((p) => [...p.slice(-(HISTORY_LIMIT - 1)), before]);
    lastRecorded.current = now;
    setFuture([]);
  }, [config]);

  const refreshRuns = useCallback(() => {
    api.runs().then(setRuns).catch(() => undefined);
  }, []);

  useEffect(() => {
    api
      .meta()
      .then((m) => {
        setMeta(m);
        const start = m.presets.find((p) => p.name === "fortification") ?? m.presets[0];
        if (start) setConfig(start.config);
      })
      .catch((e: unknown) => setLoadError(String(e)));
    refreshRuns();
  }, [refreshRuns]);

  // Live preview: debounced, and only the latest request counts.
  useEffect(() => {
    if (!config) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const task = newTaskId();
      setPreviewBusy(true);
      setPreviewTask(task);
      api
        .preview(config, previewRes, controller.signal, task)
        .then((p) => {
          setPreview(p);
          setPreviewError(null);
        })
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setPreviewError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setPreviewBusy(false);
            setPreviewTask(null);
          }
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [config, previewRes, previewAgain]);

  // Optical views of the live preview: directional light, at the chosen angle.
  useEffect(() => {
    if (!config || light === "reflected") return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .optics(config, previewRes, light, lightAngle, light === "iris" ? lightDirection : 0, controller.signal)
        .then((o) => {
          setOpticsImage(o.image);
          setOpticsNote(o.note);
        })
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setPreviewError(e instanceof Error ? e.message : String(e));
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [config, previewRes, light, lightAngle, lightDirection]);

  // Poll active jobs; refresh the run list when one finishes.
  useEffect(() => {
    const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
    if (active.length === 0) return;
    const timer = window.setInterval(() => {
      Promise.all(active.map((j) => api.job(j.id))).then((updated) => {
        setJobs((all) => all.map((j) => updated.find((u) => u.id === j.id) ?? j));
        if (updated.some((u) => u.status === "done")) refreshRuns();
      }, () => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [jobs, refreshRuns]);

  // Fetch details for the selected and pinned runs.
  useEffect(() => {
    for (const id of [selected, pinned]) {
      if (id && !details[id]) {
        api.run(id).then((d) => setDetails((all) => ({ ...all, [id]: d })), () => undefined);
      }
    }
  }, [selected, pinned, details]);

  const kind = config?.model.kind;
  const model = useMemo(() => meta?.models.find((m) => m.kind === kind) ?? null, [meta, kind]);
  const fields = useMemo(() => (model ? fieldsFor(model.schema) : []), [model]);
  const cavity = meta?.cavities.find((c) => c.name === config?.cavity.preset);
  const host = cavity?.host ?? config?.cavity.host ?? undefined;
  const drawn = config ? (drawnOf(config) ?? lastDrawn) : null;

  if (loadError) {
    return (
      <div className="fatal">
        <h1>agatesim can’t reach its server</h1>
        <p>Start it with <code>uv run agatesim serve</code>, then reload this page.</p>
        <p className="muted small">{loadError}</p>
      </div>
    );
  }
  if (!meta || !config) return <div className="fatal muted">Loading…</div>;

  // Keep the run name in step with model and cavity, unless the user has named it.
  const update = (change: (c: RunConfig) => RunConfig) =>
    setConfig((c) => {
      if (!c) return c;
      const next = change(c);
      const wasAuto = c.name === autoName(c) || meta.presets.some((p) => p.name === c.name);
      const setupChanged = next.model.kind !== c.model.kind || cavityLabel(next) !== cavityLabel(c);
      return wasAuto && setupChanged && next.name === c.name ? { ...next, name: autoName(next) } : next;
    });

  const setModelKind = (kind: string) => {
    const info = meta.models.find((m) => m.kind === kind);
    if (!info) return;
    const schedules = Object.fromEntries(info.schedules.map((v) => [v.key, v.default]));
    update((c) => ({
      ...c,
      model: {
        kind,
        ...defaultsFor(info.schema.properties),
        ...(info.schedules.length > 0 ? { schedules } : {}),
      },
      archetype: suggestedArchetype(kind, host),
    }));
  };

  // A new shape replaces the old one and its tubes (they may not fit inside).
  const setShape = (shape: Pick<RunConfig["cavity"], "preset" | "outline" | "host" | "smooth">, newHost?: string) => {
    const current = drawnOf(config);
    if (current) setLastDrawn(current);
    update((c) => {
      // Keep the judge in step with the setting, unless the user picked something else.
      const autoJudge = c.archetype === suggestedArchetype(c.model.kind, host);
      return {
        ...c,
        cavity: { ...c.cavity, ...shape, tubes: [] },
        archetype: autoJudge ? suggestedArchetype(c.model.kind, newHost) : c.archetype,
      };
    });
  };
  const setCavity = (name: string) =>
    setShape(
      { preset: name, outline: null, host: null, smooth: false },
      meta.cavities.find((c) => c.name === name)?.host,
    );
  const applyDrawn = (d: Drawn) => {
    setLastDrawn(d);
    setShape({ preset: null, outline: d.outline, host: d.host, smooth: d.smooth }, d.host);
  };

  const tubes: Tube[] = config.cavity.tubes ?? [];
  const setTubes = (next: Tube[]) => update((c) => ({ ...c, cavity: { ...c.cavity, tubes: next } }));
  const pickTube = (x: number, y: number) => {
    const hit = tubes.findIndex((t) => Math.hypot(t.x_mm - x, t.y_mm - y) <= Math.max(1, 3 * t.radius_mm));
    if (hit >= 0) setTubes(tubes.filter((_, i) => i !== hit));
    else setTubes([...tubes, { x_mm: round2(x), y_mm: round2(y), radius_mm: tubeRadius }]);
  };

  /** Save a self-contained report of the shown result: a saved run, or the preview. */
  const exportReport = async () => {
    try {
      const run = selected ? selectedDetail : undefined;
      const shown = run ? run.config : config;
      const image = run ? await dataUrl(api.slabUrl(run.id)) : preview?.image;
      if (!image) return;
      const html = buildReport({
        config: shown,
        image,
        evaluation: run ? run.evaluation : (preview?.evaluation ?? null),
        stats: run ? run.stats : (preview?.stats ?? null),
        archetypes: meta.archetypes,
        models: meta.models,
        description: meta.presets.find((p) => p.name === shown.name)?.description,
        source: run ? `saved run ${run.metadata.grid.nx}×${run.metadata.grid.ny} px` : `preview ${preview?.width ?? ""}×${preview?.height ?? ""} px`,
        commit: run?.metadata.git.commit,
        created: new Date(),
      });
      saveBlob(new Blob([html], { type: "text/html" }), `${shown.name}-report.html`);
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : String(e));
    }
  };

  const startRun = () => {
    const runConfig = { ...config, grid: { ...config.grid, resolution: runResolution } };
    api.startRun(runConfig).then(
      (job) => setJobs((all) => [job, ...all]),
      (e: unknown) => setPreviewError(e instanceof Error ? e.message : String(e)),
    );
  };

  const undo = () => {
    const last = past[past.length - 1];
    if (!last) return;
    travelling.current = true;
    setPast(past.slice(0, -1));
    setFuture([config, ...future]);
    setConfig(last);
  };
  const redo = () => {
    const [next, ...later] = future;
    if (!next) return;
    travelling.current = true;
    setFuture(later);
    setPast([...past, config]);
    setConfig(next);
  };

  const randomizable = fields.length > 0 && JSON.stringify(model?.schema ?? {}).includes('"explore"');
  // Extras Randomize may vary, where they apply to this model.
  const extraOptions: [RandomizeExtra, string, string][] = [
    ["cavity", "cavity", "Another shape of the same host, size within ±30%, any rotation (not with tubes placed)"],
    ...(model && model.schedules.length > 0
      ? ([["schedules", "timelines", "Shift timeline events by up to 10% of the run; vary silica and iron levels"]] as [RandomizeExtra, string, string][])
      : []),
    ...(config.model.kind === "mechanistic-staged"
      ? ([["order", "stage order", "A random stage order from the allowed list"]] as [RandomizeExtra, string, string][])
      : []),
  ];
  const randomize = () => {
    const task = newTaskId();
    const controller = new AbortController();
    randomAbort.current = controller;
    setRandomTask(task);
    setRandomNote("");
    const allowed = extras.filter((x) => extraOptions.some(([key]) => key === x));
    api.randomize(config, strength, keepForm && !!config.archetype, allowed, controller.signal, task).then(
      (r) => {
        if (r.accepted) setConfig(r.config);
        setRandomNote(
          r.note || (r.checked ? `checked: ${r.attempts} ${r.attempts === 1 ? "draw" : "draws"}` : ""),
        );
      },
      (e: unknown) => {
        if (!controller.signal.aborted) setRandomNote(e instanceof Error ? e.message : String(e));
      },
    ).finally(() => setRandomTask((t) => (t === task ? null : t)));
  };
  const cancelRandomize = () => {
    randomAbort.current?.abort();
    setRandomTask(null);
    setRandomNote("Randomize cancelled; settings unchanged");
  };

  // Choosing a form loads its preset for the current tier (or the other tier's, if
  // this one has none) and judges the result as that form.
  const forms = formPresets(meta);
  const others = otherPresets(meta);
  const tier = tierOf(config.model.kind);
  const chooseForm = (id: string, wanted = tier) => {
    if (!id) {
      update((c) => ({ ...c, archetype: null }));
      return;
    }
    const pair = forms.find((f) => f.id === id);
    const preset = pair?.[wanted] ?? pair?.[wanted === "procedural" ? "mechanistic" : "procedural"];
    if (preset) setConfig(preset.config);
    else update((c) => ({ ...c, archetype: id }));
  };

  const selectedDetail = selected ? details[selected] : undefined;
  const pinnedDetail = pinned && pinned !== selected ? details[pinned] : undefined;

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand">
          agatesim <span className="muted small">v{meta.version}</span>
        </h1>
        <div className="toggle" role="radiogroup" aria-label="Screen">
          {(
            [
              ["simulator", "Simulator"],
              ["twoways", "Two ways"],
              ["volume", "3D"],
              ["specimens", "Specimens"],
            ] as const
          ).map(([s, label]) => (
            <button key={s} type="button" role="radio" aria-checked={screen === s} onClick={() => setScreen(s)}>
              {label}
            </button>
          ))}
        </div>
        <Tour />
        <Glossary />
        {screen === "simulator" && (
        <>
        <div className="run-controls">
          <label className="inline">
            <span className="micro-label">Resolution</span>
            <select id="run-resolution" value={runResolution} onChange={(e) => setRunResolution(Number(e.target.value))}>
              {RUN_RESOLUTIONS.map((r) => (
                <option key={r} value={r}>
                  {r} px
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="primary" onClick={startRun} title={`Saved as “${config.name}”`}>
            Run full resolution
          </button>
        </div>
        </>
        )}
      </header>

      {screen === "twoways" ? (
        <TwoWays
          meta={meta}
          resolution={Math.min(512, meta.limits.preview)}
          onOpen={(c) => {
            setConfig(c);
            setSelected(null);
            setScreen("simulator");
          }}
        />
      ) : screen === "volume" ? (
        <VolumeWorkbench models={meta.models} archetypes={meta.archetypes} />
      ) : screen === "specimens" ? (
        <SpecimenWorkbench
          onOpenReplica={(replica) => {
            setConfig(replica);
            setSelected(null);
            setScreen("simulator");
          }}
        />
      ) : (
      <div className="workspace">
        <aside className="controls" aria-label="Simulation settings">
          <div className="randomize">
            {preview && (
              <img className="mobile-thumb" src={preview.image} alt="Current preview" aria-hidden="true" />
            )}
            <div className="history" role="group" aria-label="Settings history">
              <button type="button" onClick={undo} disabled={past.length === 0} title="Undo the last settings change">
                Undo
              </button>
              <button type="button" onClick={redo} disabled={future.length === 0} title="Redo">
                Redo
              </button>
            </div>
            {randomizable && (
              <>
              <button type="button" onClick={randomize} disabled={randomizing} title="Move the key settings toward random values within their bounded ranges">
                {randomizing ? "Randomizing…" : "Randomize"}
              </button>
              <label className="inline small">
                <span className="micro-label">How far</span>
                <select id="random-strength" value={strength} onChange={(e) => setStrength(Number(e.target.value))}>
                  {STRENGTHS.map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="inline small" title={config.archetype ? "Keep only draws that still pass the form's tests (slower)" : "Choose a form first"}>
                <input
                  type="checkbox"
                  checked={keepForm && !!config.archetype}
                  disabled={!config.archetype}
                  onChange={(e) => setKeepForm(e.target.checked)}
                />
                Stay within the form
              </label>
              <span className="inline small extras" role="group" aria-label="Also vary">
                <span className="micro-label">Also vary</span>
                {extraOptions.map(([key, label, help]) => (
                  <label key={key} className="inline small" title={help}>
                    <input
                      type="checkbox"
                      checked={extras.includes(key)}
                      onChange={(e) =>
                        setExtras((xs) => (e.target.checked ? [...xs, key] : xs.filter((x) => x !== key)))
                      }
                    />
                    {label}
                  </label>
                ))}
              </span>
              </>
            )}
            <TaskProgress task={randomTask} title="Randomizing" onCancel={cancelRandomize} />
            {randomNote && <span className="muted small" aria-live="polite">{randomNote}</span>}
          </div>
          <section>
            <h2>Form</h2>
            <p className="param-help">Start from a form's verified settings; the result is judged as that form.</p>
            <select id="form" value={config.archetype ?? ""} onChange={(e) => chooseForm(e.target.value)}>
              <option value="">No form (don't judge)</option>
              {forms.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
            {config.archetype && forms.some((f) => f.id === config.archetype) && (
              <div className="segmented tier" role="radiogroup" aria-label="Tier">
                {(["procedural", "mechanistic"] as const).map((t) => {
                  const pair = forms.find((f) => f.id === config.archetype);
                  return (
                    <button
                      key={t}
                      type="button"
                      role="radio"
                      aria-checked={tier === t}
                      disabled={!pair?.[t]}
                      title={pair?.[t] ? `Load the ${t} preset` : `No ${t} preset for this form`}
                      onClick={() => config.archetype && chooseForm(config.archetype, t)}
                    >
                      {t === "procedural" ? "Procedural" : "Mechanistic"}
                    </button>
                  );
                })}
              </div>
            )}
            {others.length > 0 && (
              <label className="inline small other-presets">
                <span className="micro-label">Other presets</span>
                <select
                  id="other-preset"
                  value=""
                  onChange={(e) => {
                    const p = others.find((x) => x.name === e.target.value);
                    if (p) setConfig(p.config);
                  }}
                >
                  <option value="" disabled>
                    Load…
                  </option>
                  {others.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </section>

          <section>
            <h2>Model</h2>
            {(["procedural", "mechanistic"] as const).map((group) => (
              <div key={group} className="model-group">
                <span className="micro-label">{group === "procedural" ? "Procedural (by design)" : "Mechanistic (from physics)"}</span>
                <div className="segmented" role="radiogroup" aria-label={`${group} models`}>
                  {meta.models
                    .filter((m) => tierOf(m.kind) === group)
                    .map((m) => (
                      <button
                        key={m.kind}
                        type="button"
                        role="radio"
                        aria-checked={m.kind === config.model.kind}
                        onClick={() => setModelKind(m.kind)}
                      >
                        {m.title}
                      </button>
                    ))}
                </div>
              </div>
            ))}
          </section>

          <section>
            <h2>Cavity</h2>
            <CavityMenu
              cavities={meta.cavities}
              selected={config.cavity.preset ?? null}
              drawn={drawn}
              onSelect={setCavity}
              onUseDrawn={() => drawn && applyDrawn(drawn)}
              onDraw={(edit) => setDrawer(edit ? "edit" : "new")}
            />
            <Slider
              id="cavity-size"
              control={SIZE_CONTROL}
              value={config.cavity.size_mm}
              onChange={(v) => update((c) => ({ ...c, cavity: { ...c.cavity, size_mm: v } }))}
            />
            <Slider
              id="cavity-rotation"
              control={ROTATION_CONTROL}
              value={config.cavity.rotation_deg}
              onChange={(v) => update((c) => ({ ...c, cavity: { ...c.cavity, rotation_deg: v } }))}
            />
            <TubePanel
              tubes={tubes}
              placing={placingTubes && selected === null}
              radius={tubeRadius}
              onPlacing={(on) => {
                setPlacingTubes(on);
                if (on) setSelected(null);
              }}
              onRadius={setTubeRadius}
              onClear={() => setTubes([])}
            />
          </section>

          <section>
            <h2>Parameters</h2>
            <ParamPanel
              fields={fields}
              values={config.model}
              onChange={(path, v) => update((c) => ({ ...c, model: { ...withSetting(c.model, path, v), kind: c.model.kind } }))}
            />
          </section>

          {model && model.schedules.length > 0 && (
            <section>
              <h2>Conditions over time</h2>
              {model.schedules.map((v) => (
                <ScheduleEditor
                  key={v.key}
                  variable={v}
                  schedule={config.model.schedules?.[v.key] ?? v.default}
                  onChange={(s) =>
                    update((c) => ({
                      ...c,
                      model: { ...c.model, schedules: { ...c.model.schedules, [v.key]: s } },
                    }))
                  }
                />
              ))}
            </section>
          )}

          <section>
            <h2>Seed</h2>
            <div className="seed">
              <label htmlFor="seed">Seed</label>
              <input
                id="seed"
                type="number"
                min={0}
                value={config.seed}
                onChange={(e) => update((c) => ({ ...c, seed: Math.max(0, Math.floor(Number(e.target.value) || 0)) }))}
              />
              <button
                type="button"
                onClick={() => update((c) => ({ ...c, seed: Math.floor(Math.random() * 1_000_000) }))}
              >
                New seed
              </button>
            </div>
          </section>
        </aside>

        <main className="viewer">
          <div className="tabs" role="tablist">
            <button type="button" role="tab" aria-selected={selected === null} onClick={() => setSelected(null)}>
              Live preview
            </button>
            {selected && (
              <button type="button" role="tab" aria-selected="true">
                Run: {selectedDetail?.config.name ?? selected}
              </button>
            )}
            <span className="tab-status muted small" aria-live="polite">
              {selected === null &&
                (previewError
                  ? ""
                  : previewBusy
                    ? "Updating…"
                    : preview
                      ? `${preview.width}×${preview.height} px · ${preview.elapsed_ms} ms`
                      : "")}
            </span>
            {selected === null && (
              <div className="light-controls">
                <div className="toggle" role="radiogroup" aria-label="Lighting">
                  {(
                    [
                      ["reflected", "Slab"],
                      ["shadow", "Shadow"],
                      ["iris", "Iris"],
                    ] as const
                  ).map(([v, label]) => (
                    <button
                      key={v}
                      type="button"
                      role="radio"
                      aria-checked={light === v}
                      title={
                        v === "reflected"
                          ? "Polished slab in diffuse reflected light"
                          : v === "shadow"
                            ? "Reflected light from one direction: shadows inside clear bands move with it"
                            : "Backlit thin slice seen off-axis: fine micro-banding diffracts colours"
                      }
                      onClick={() => setLight(v)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {light !== "reflected" && (
                  <label className="inline small">
                    <span className="micro-label">{light === "shadow" ? "Light angle" : "View angle"}</span>
                    <input
                      id="light-angle"
                      type="range"
                      min={-60}
                      max={60}
                      step={1}
                      value={lightAngle}
                      onChange={(e) => setLightAngle(Number(e.target.value))}
                    />
                    <output htmlFor="light-angle">{lightAngle}°</output>
                  </label>
                )}
                {light === "iris" && (
                  <label className="inline small" title="Which way the view tilts off the light, in the slab plane">
                    <span className="micro-label">Direction</span>
                    <input
                      id="light-direction"
                      type="range"
                      min={0}
                      max={180}
                      step={5}
                      value={lightDirection}
                      onChange={(e) => setLightDirection(Number(e.target.value))}
                    />
                    <output htmlFor="light-direction">{lightDirection}°</output>
                  </label>
                )}
              </div>
            )}
            {selected === null && (
              <label className="inline small">
                <span className="micro-label">Preview</span>
                <select id="preview-resolution" value={previewRes} onChange={(e) => setPreviewRes(Number(e.target.value))}>
                  {PREVIEW_RESOLUTIONS.map((r) => (
                    <option key={r} value={r}>
                      {r} px
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {selected === null && light === "iris" && opticsNote && (
            <p className="muted small" role="status">
              {opticsNote}
            </p>
          )}
          {selected === null && previewBusy && (
            <TaskProgress
              task={previewTask}
              title="Simulating the preview"
              onCancel={() => previewTask && void progressApi.cancel(previewTask)}
            />
          )}
          {selected === null && previewError === "cancelled" && (
            <p className="muted small" role="status">
              Preview stopped. Change a setting, or{" "}
              <button type="button" className="link-button" onClick={() => setPreviewAgain((n) => n + 1)}>
                run it again
              </button>
              .
            </p>
          )}
          {selected === null && previewError && previewError !== "cancelled" && (
            <p className="error" role="alert">
              This configuration can’t run: {previewError}
            </p>
          )}

          {pinnedDetail && (
            <div className="compare-growth">
              <label className="inline small">
                <input type="checkbox" checked={linkGrowth} onChange={(e) => setLinkGrowth(e.target.checked)} />
                Grow both together
              </label>
              {linkGrowth && (
                <GrowthControls
                  id="compare"
                  value={sharedGrowth}
                  onChange={setSharedGrowth}
                  stages={selected ? selectedDetail?.stages : preview?.stages}
                />
              )}
            </div>
          )}
          <div className={`slabs${pinnedDetail ? " compare" : ""}`}>
            {selected === null && preview && (
              <SlabView
                identity="preview"
                imageSrc={light !== "reflected" && opticsImage ? opticsImage : preview.image}
                tdepSrc={preview.tdep}
                dxMm={preview.dx_mm}
                stages={preview.stages}
                growth={pinnedDetail && linkGrowth ? sharedGrowth : undefined}
                exportName={`${config.name}-growth`}
                caption={`Preview of “${config.name}”`}
                picking={
                  placingTubes
                    ? {
                        grid: { x0: preview.x0_mm, y1: preview.y1_mm, dx: preview.dx_mm },
                        markers: tubes.map((t) => ({ x: t.x_mm, y: t.y_mm, r: t.radius_mm })),
                        onPick: pickTube,
                      }
                    : undefined
                }
              />
            )}
            {selected && selectedDetail && (
              <SlabView
                identity={selected}
                imageSrc={api.slabUrl(selected)}
                tdepSrc={api.tdepUrl(selected)}
                dxMm={selectedDetail.metadata.grid.dx_mm}
                stages={selectedDetail.stages}
                growth={pinnedDetail && linkGrowth ? sharedGrowth : undefined}
                exportName={`${selectedDetail.config.name}-growth`}
                caption={`${selectedDetail.config.name} · ${selectedDetail.metadata.grid.nx}×${selectedDetail.metadata.grid.ny} px`}
              />
            )}
            {pinnedDetail && pinned && (
              <SlabView
                identity={`pinned-${pinned}`}
                imageSrc={api.slabUrl(pinned)}
                tdepSrc={api.tdepUrl(pinned)}
                dxMm={pinnedDetail.metadata.grid.dx_mm}
                stages={pinnedDetail.stages}
                growth={linkGrowth ? sharedGrowth : undefined}
                exportName={`${pinnedDetail.config.name}-growth`}
                caption={`Pinned: ${pinnedDetail.config.name}`}
              />
            )}
          </div>

          {(selected ? selectedDetail : preview) && (
            <div className="run-actions">
              {selected && selectedDetail && (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      setConfig(selectedDetail.config);
                      setSelected(null);
                    }}
                  >
                    Use these settings
                  </button>
                  <button type="button" onClick={() => setPinned(pinned === selected ? null : selected)}>
                    {pinned === selected ? "Unpin" : "Pin for comparison"}
                  </button>
                </>
              )}
              {selected === null && pinned && (
                <button type="button" onClick={() => setPinned(null)}>
                  Unpin {details[pinned]?.config.name ?? "run"}
                </button>
              )}
              <button type="button" onClick={() => void exportReport()}>
                Export report
              </button>
            </div>
          )}

          <div className={pinnedDetail ? "criteria-compare" : undefined}>
            <CriteriaPanel
              evaluation={selected ? (selectedDetail?.evaluation ?? null) : (preview?.evaluation ?? null)}
              archetypes={meta.archetypes}
              title={pinnedDetail ? (selected ? (selectedDetail?.config.name ?? "run") : "Preview") : undefined}
            />
            {pinnedDetail && (
              <CriteriaPanel
                evaluation={pinnedDetail.evaluation ?? null}
                archetypes={meta.archetypes}
                title={`Pinned: ${pinnedDetail.config.name}`}
              />
            )}
          </div>

          {pinnedDetail && (selected ? selectedDetail : config) && (
            <RunDiff
              a={{
                title: selected ? (selectedDetail?.config.name ?? "run") : "Preview",
                config: selected && selectedDetail ? selectedDetail.config : config,
              }}
              b={{ title: `Pinned: ${pinnedDetail.config.name}`, config: pinnedDetail.config }}
            />
          )}

          <StatsPanel
            columns={[
              {
                title: selected ? (selectedDetail?.config.name ?? "run") : "Preview",
                stats: selected ? (selectedDetail?.stats ?? null) : (preview?.stats ?? null),
              },
              ...(pinnedDetail ? [{ title: `Pinned: ${pinnedDetail.config.name}`, stats: pinnedDetail.stats }] : []),
            ]}
          />

        </main>

        <RunBrowser runs={runs} jobs={jobs} selected={selected} pinned={pinned} onSelect={setSelected} />
      </div>
      )}
      {drawer && (
        <CavityDrawer
          initial={drawer === "edit" ? drawn : null}
          onUse={(d) => {
            applyDrawn(d);
            setDrawer(null);
          }}
          onCancel={() => setDrawer(null)}
        />
      )}
    </div>
  );
}

/** An image the server serves, as a data: URL for embedding in a report. */
async function dataUrl(url: string): Promise<string> {
  const blob = await (await fetch(url)).blob();
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("couldn't read the slab image"));
    reader.readAsDataURL(blob);
  });
}
