import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  type Job,
  type Meta,
  type PreviewResult,
  type RunConfig,
  type RunDetail,
  type RunSummary,
  type Tube,
} from "./api";
import { CavityDrawer, type Drawn } from "./components/CavityDrawer";
import { CavityMenu } from "./components/CavityMenu";
import { CriteriaPanel } from "./components/CriteriaPanel";
import { ParamPanel, Slider } from "./components/ParamPanel";
import { RunBrowser } from "./components/RunBrowser";
import { ScheduleEditor } from "./components/ScheduleEditor";
import { SlabView } from "./components/SlabView";
import { SpecimenWorkbench } from "./components/SpecimenWorkbench";
import { StatsPanel } from "./components/StatsPanel";
import { TubePanel } from "./components/TubePanel";
import { VolumeWorkbench } from "./components/VolumeWorkbench";
import { type Control, controlsFor, defaultsFor } from "./lib/schema";
import { CompareMechanisms } from "./components/CompareMechanisms";
import { Glossary } from "./components/Glossary";

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

function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+/, "").slice(0, 40) || "run";
}

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [config, setConfig] = useState<RunConfig | null>(null);
  const [previewRes, setPreviewRes] = useState(256);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [runResolution, setRunResolution] = useState(768);
  const [selected, setSelected] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, RunDetail>>({});
  const [drawer, setDrawer] = useState<"edit" | "new" | null>(null);
  const [lastDrawn, setLastDrawn] = useState<Drawn | null>(null);
  const [placingTubes, setPlacingTubes] = useState(false);
  const [tubeRadius, setTubeRadius] = useState(0.3);
  const [screen, setScreen] = useState<"simulator" | "volume" | "specimens">("simulator");
  const [light, setLight] = useState<"reflected" | "shadow" | "iris">("reflected");
  const [lightAngle, setLightAngle] = useState(30);
  const [opticsImage, setOpticsImage] = useState<string | null>(null);

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
      setPreviewBusy(true);
      api
        .preview(config, previewRes, controller.signal)
        .then((p) => {
          setPreview(p);
          setPreviewError(null);
        })
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setPreviewError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (!controller.signal.aborted) setPreviewBusy(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [config, previewRes]);

  // Optical views of the live preview: directional light, at the chosen angle.
  useEffect(() => {
    if (!config || light === "reflected") return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .optics(config, previewRes, light, lightAngle, controller.signal)
        .then((o) => setOpticsImage(o.image))
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setPreviewError(e instanceof Error ? e.message : String(e));
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [config, previewRes, light, lightAngle]);

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
  const controls = useMemo(() => (model ? controlsFor(model.schema.properties) : []), [model]);
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

  const startRun = () => {
    const runConfig = { ...config, grid: { ...config.grid, resolution: runResolution } };
    api.startRun(runConfig).then(
      (job) => setJobs((all) => [job, ...all]),
      (e: unknown) => setPreviewError(e instanceof Error ? e.message : String(e)),
    );
  };

  const selectedDetail = selected ? details[selected] : undefined;
  const pinnedDetail = pinned && pinned !== selected ? details[pinned] : undefined;
  const judgeable = meta.archetypes.filter((a) => a.implemented);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          agatesim <span className="muted small">v{meta.version}</span>
        </div>
        <div className="toggle" role="radiogroup" aria-label="Screen">
          {(
            [
              ["simulator", "Simulator"],
              ["volume", "3D"],
              ["specimens", "Specimens"],
            ] as const
          ).map(([s, label]) => (
            <button key={s} type="button" role="radio" aria-checked={screen === s} onClick={() => setScreen(s)}>
              {label}
            </button>
          ))}
        </div>
        <Glossary />
        {screen === "simulator" && (
        <>
        <label className="inline">
          <span className="micro-label">Preset</span>
          <select
            id="preset"
            value=""
            onChange={(e) => {
              const p = meta.presets.find((x) => x.name === e.target.value);
              if (p) setConfig(p.config);
            }}
          >
            <option value="" disabled>
              Load a preset…
            </option>
            {meta.presets.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <div className="run-controls">
          <label className="inline">
            <span className="micro-label">Name</span>
            <input
              id="run-name"
              value={config.name}
              onChange={(e) => update((c) => ({ ...c, name: slug(e.target.value) }))}
            />
          </label>
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
          <button type="button" className="primary" onClick={startRun}>
            Run full resolution
          </button>
        </div>
        </>
        )}
      </header>

      {screen === "volume" ? (
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
          <section>
            <h2>Model</h2>
            <div className="segmented" role="radiogroup" aria-label="Model">
              {meta.models.map((m) => (
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
              controls={controls}
              values={config.model}
              onChange={(key, v) => update((c) => ({ ...c, model: { ...c.model, [key]: v } }))}
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
            <h2>Judge as</h2>
            <select
              id="archetype"
              value={config.archetype ?? ""}
              onChange={(e) => update((c) => ({ ...c, archetype: e.target.value || null }))}
            >
              <option value="">No archetype</option>
              {judgeable.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
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

          {selected === null && previewError && (
            <p className="error" role="alert">
              This configuration can’t run: {previewError}
            </p>
          )}

          <div className={`slabs${pinnedDetail ? " compare" : ""}`}>
            {selected === null && preview && (
              <SlabView
                identity="preview"
                imageSrc={light !== "reflected" && opticsImage ? opticsImage : preview.image}
                tdepSrc={preview.tdep}
                dxMm={preview.dx_mm}
                stages={preview.stages}
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
                exportName={`${pinnedDetail.config.name}-growth`}
                caption={`Pinned: ${pinnedDetail.config.name}`}
              />
            )}
          </div>

          {selected && selectedDetail && (
            <div className="run-actions">
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
            </div>
          )}
          {selected === null && pinned && (
            <div className="run-actions">
              <button type="button" onClick={() => setPinned(null)}>
                Unpin {details[pinned]?.config.name ?? "run"}
              </button>
            </div>
          )}

          <CriteriaPanel
            evaluation={selected ? (selectedDetail?.evaluation ?? null) : (preview?.evaluation ?? null)}
            archetypes={meta.archetypes}
          />

          <StatsPanel
            columns={[
              {
                title: selected ? (selectedDetail?.config.name ?? "run") : "Preview",
                stats: selected ? (selectedDetail?.stats ?? null) : (preview?.stats ?? null),
              },
              ...(pinnedDetail ? [{ title: `Pinned: ${pinnedDetail.config.name}`, stats: pinnedDetail.stats }] : []),
            ]}
          />

          <CompareMechanisms config={config} models={meta.models} resolution={Math.min(512, meta.limits.preview)} gpu={meta.gpu} />
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
