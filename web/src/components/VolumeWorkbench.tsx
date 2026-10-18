import { useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type ArchetypeInfo,
  type CutResult,
  type Job,
  type ModelInfo,
  type SliceConfig,
  type SurveyResult,
  type VolumeConfig,
  type VolumeMeta,
  type VolumeRunSummary,
  type VoxelVolume,
  progress as progressApi,
  volume as volumeApi,
} from "../api";
import { captioned, type FrameSource } from "../lib/animation";
import { newTaskId } from "../lib/progress";
import { type Control, defaultsFor, fieldsFor, withSetting } from "../lib/schema";
import { ExportAnimation } from "./ExportAnimation";
import { CriteriaPanel } from "./CriteriaPanel";
import { GrowthControls } from "./GrowthControls";
import { ParamPanel, Slider } from "./ParamPanel";
import { SlabView, slabSource, useSlabPixels } from "./SlabView";
import { StatsPanel } from "./StatsPanel";
import { TaskProgress } from "./TaskProgress";
import { Volume3D, type Volume3DHandle } from "./Volume3D";
import { VolumeRuns } from "./VolumeRuns";

const CUT_RESOLUTIONS = [256, 384, 512, 768];
const VIEW_RESOLUTIONS = [64, 96, 128];
const RUN_RESOLUTIONS = [128, 192, 256];
const SURVEY_COUNTS = [20, 40, 100];
const DEBOUNCE_MS = 250;
// In 3D, gravity is a direction in space, set below, not an angle in the slab.
const HIDDEN_PARAMS = new Set(["gravity_deg"]);

const control = (
  key: string,
  label: string,
  units: string,
  description: string,
  min: number,
  max: number,
  step: number,
  defaultValue: number,
): Control => ({ key, label, units, nature: "physical", description, min, max, step, defaultValue });

const SIZE = control("size_mm", "Cavity size", "mm", "Longest dimension of the cavity.", 10, 150, 1, 50);
const YAW = control("yaw_deg", "Turn", "deg", "Turns the cavity about the vertical axis.", -180, 180, 1, 0);
const PITCH = control("pitch_deg", "Tilt", "deg", "Tilts the cavity's long axis up from horizontal.", -90, 90, 1, 0);
const G_TILT = control("tilt_deg", "Gravity tilt", "deg", "Tilt of gravity from straight down.", 0, 90, 1, 0);
const G_AZIMUTH = control(
  "azimuth_deg", "Gravity direction", "deg", "Which way gravity tilts, anticlockwise from +x.", -180, 180, 1, 0,
);
const CUT_TILT = control(
  "tilt_deg", "Cut tilt", "deg", "Tilt of the cut's normal from vertical (90 = a vertical cut).", 0, 180, 1, 90,
);
const CUT_AZIMUTH = control(
  "azimuth_deg", "Cut direction", "deg", "Direction the cut faces, anticlockwise from +x.", -180, 360, 1, 270,
);

const CUT_VIEWS: [string, Partial<SliceConfig>][] = [
  ["Front", { tilt_deg: 90, azimuth_deg: 270, offset_mm: 0 }],
  ["Side", { tilt_deg: 90, azimuth_deg: 0, offset_mm: 0 }],
  ["Top", { tilt_deg: 0, azimuth_deg: 0, offset_mm: 0 }],
];

/** The 3D view (as shown on screen) beside the cut, at the cut's height. */
function sideBySide(view: Volume3DHandle | null, cut: FrameSource): FrameSource {
  const gap = 8;
  const probe = view?.renderAt(1);
  const w3 = probe ? Math.round((probe.width / Math.max(probe.height, 1)) * cut.height) : 0;
  return {
    width: w3 + (w3 ? gap : 0) + cut.width,
    height: cut.height,
    draw: (ctx, t) => {
      ctx.fillStyle = "#121316";
      ctx.fillRect(0, 0, w3 + gap + cut.width, cut.height);
      const canvas = view?.renderAt(t);
      if (canvas && w3) ctx.drawImage(canvas, 0, 0, w3, cut.height);
      ctx.save();
      ctx.translate(w3 + (w3 ? gap : 0), 0);
      cut.draw(ctx, t);
      ctx.restore();
    },
  };
}

/** A request the server stopped because it was cancelled, in words. */
const STOPPED = "Stopped. Change a setting, or press Rebuild, to build it again.";
const message = (e: unknown) => {
  const text = e instanceof Error ? e.message : String(e);
  return text === "cancelled" ? STOPPED : text;
};

const pct = (r: number | null | undefined) => (r === null || r === undefined ? "n/a" : `${Math.round(r * 100)}%`);

interface Props {
  models: ModelInfo[];
  archetypes: ArchetypeInfo[];
}

/** 3D runs: a cavity as a solid, a rotatable view and the cut that a collector sees. */
export function VolumeWorkbench({ models, archetypes }: Props) {
  const [meta, setMeta] = useState<VolumeMeta | null>(null);
  const [config, setConfig] = useState<VolumeConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [cutRes, setCutRes] = useState(384);
  const [viewRes, setViewRes] = useState(96);
  const [cut, setCut] = useState<CutResult | null>(null);
  const [cutBusy, setCutBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voxels, setVoxels] = useState<VoxelVolume | null>(null);
  const [voxelsBusy, setVoxelsBusy] = useState(false);
  // Progress ids of the requests in flight, and a counter that rebuilds on demand.
  const [cutTask, setCutTask] = useState<string | null>(null);
  const [voxelsTask, setVoxelsTask] = useState<string | null>(null);
  const [rebuild, setRebuild] = useState(0);
  const [surveyCount, setSurveyCount] = useState(40);
  const [surveyed, setSurveyed] = useState<{ key: string; result: SurveyResult } | null>(null);
  const [surveyTask, setSurveyTask] = useState<string | null>(null);
  const surveyAbort = useRef<AbortController | null>(null);
  const [runRes, setRunRes] = useState(192);
  const [job, setJob] = useState<Job | null>(null);
  const [growth, setGrowth] = useState(1);
  const [savedRuns, setSavedRuns] = useState<VolumeRunSummary[]>([]);
  const [opening, setOpening] = useState<string | null>(null);
  const view3d = useRef<Volume3DHandle | null>(null);
  const cutPixels = useSlabPixels(cut?.image ?? "", cut?.tdep ?? "");

  useEffect(() => {
    volumeApi
      .meta()
      .then((m) => {
        setMeta(m);
        const start = m.presets.find((p) => p.name === "fortification-mechanistic-3d") ?? m.presets[0];
        if (start) setConfig(start.config);
      })
      .catch((e: unknown) => setLoadError(String(e)));
  }, []);

  // The cut: debounced, and only the latest request counts.
  useEffect(() => {
    if (!config) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const task = newTaskId();
      setCutBusy(true);
      setCutTask(task);
      volumeApi
        .cut(config, cutRes, controller.signal, task)
        .then((c) => {
          setCut(c);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setError(message(e));
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setCutBusy(false);
            setCutTask(null);
          }
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [config, cutRes, rebuild]);

  // The 3D view depends on the formation only, not on the cut.
  const formationKey = config
    ? JSON.stringify({ solid: config.solid, gravity: config.gravity, model: config.model, seed: config.seed })
    : "";
  useEffect(() => {
    if (!config) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const task = newTaskId();
      setVoxelsBusy(true);
      setVoxelsTask(task);
      volumeApi
        .voxels(config, viewRes, controller.signal, task)
        .then(setVoxels)
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setError(message(e));
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setVoxelsBusy(false);
            setVoxelsTask(null);
          }
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- formationKey stands for config's formation
  }, [formationKey, viewRes, rebuild]);

  // A survey belongs to one formation and archetype: hide it once either changes.
  const surveyKey = `${formationKey}|${config?.archetype ?? ""}`;
  const survey = surveyed?.key === surveyKey ? surveyed.result : null;

  // Saved runs: on opening the screen, and again when a run finishes.
  useEffect(() => {
    if (job && job.status !== "done") return;
    volumeApi.runs().then(setSavedRuns, () => undefined);
  }, [job]);

  // Follow a full run until it finishes.
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const timer = window.setInterval(() => {
      api.job(job.id).then(setJob, () => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [job]);

  const kind = config?.model.kind;
  const model = useMemo(() => models.find((m) => m.kind === kind) ?? null, [models, kind]);
  const fields = useMemo(
    () => (model ? fieldsFor(model.schema).filter((f) => !HIDDEN_PARAMS.has(f.key)) : []),
    [model],
  );

  if (loadError) return <p className="error">Can’t load the 3D settings: {loadError}</p>;
  if (!meta || !config) return <div className="fatal muted">Loading…</div>;

  const update = (change: (c: VolumeConfig) => VolumeConfig) => setConfig((c) => (c ? change(c) : c));
  const setSlice = (s: Partial<SliceConfig>) => update((c) => ({ ...c, slice: { ...c.slice, ...s } }));
  const setModelKind = (k: string) => {
    const info = models.find((m) => m.kind === k);
    if (!info) return;
    update((c) => ({ ...c, model: { kind: k, ...defaultsFor(info.schema.properties) } }));
  };
  const judgeable = archetypes.filter((a) => a.implemented);
  const half = config.solid.size_mm / 2;
  const OFFSET = control(
    "offset_mm", "Cut offset", "mm", "Moves the cut along its normal from the cavity's centre.", -half, half, 0.5, 0,
  );

  const runSurvey = () => {
    const task = newTaskId();
    const controller = new AbortController();
    surveyAbort.current = controller;
    setSurveyTask(task);
    volumeApi
      .survey(config, surveyCount, 384, controller.signal, task)
      .then(
        (result) => setSurveyed({ key: surveyKey, result }),
        (e: unknown) => {
          if (!controller.signal.aborted) setError(message(e));
        },
      )
      .finally(() => setSurveyTask((t) => (t === task ? null : t)));
  };
  const cancelSurvey = () => {
    surveyAbort.current?.abort();
    setSurveyTask(null);
  };
  // Stop building the 3D view and its cut (the server stops too).
  const cancelBuild = () => {
    for (const task of [voxelsTask, cutTask]) if (task) void progressApi.cancel(task);
  };
  const surveyBusy = surveyTask !== null;
  const jobRunning = job !== null && (job.status === "queued" || job.status === "running");
  const openRun = (id: string) => {
    setOpening(id);
    volumeApi
      .run(id)
      .then(
        (detail) => setConfig(detail.config),
        (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setOpening(null));
  };
  const startRun = () => {
    volumeApi
      .startRun({ ...config, grid: { ...config.grid, resolution: runRes } }, config.archetype ? 40 : 0)
      .then(setJob, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  };

  return (
    <div className="workspace volume">
      <aside className="controls" aria-label="3D settings">
        <section>
          <h2>Preset</h2>
          <select
            id="volume-preset"
            value=""
            onChange={(e) => {
              const p = meta.presets.find((x) => x.name === e.target.value);
              if (p) setConfig(p.config);
            }}
          >
            <option value="" disabled>
              Load a 3D preset…
            </option>
            {meta.presets.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
        </section>

        <section>
          <h2>Model</h2>
          <div className="segmented" role="radiogroup" aria-label="Model">
            {models
              .filter((m) => meta.kinds.includes(m.kind))
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
        </section>

        <section>
          <h2>Cavity</h2>
          <div className="segmented" role="radiogroup" aria-label="Cavity shape">
            {meta.solids.map((s) => (
              <button
                key={s.name}
                type="button"
                role="radio"
                title={s.description}
                aria-checked={config.solid.preset === s.name}
                onClick={() => update((c) => ({ ...c, solid: { ...c.solid, preset: s.name, outline: null, host: null } }))}
              >
                {s.name}
              </button>
            ))}
          </div>
          <Slider id="solid-size" control={SIZE} value={config.solid.size_mm}
            onChange={(v) => update((c) => ({ ...c, solid: { ...c.solid, size_mm: v } }))} />
          <Slider id="solid-yaw" control={YAW} value={config.solid.yaw_deg}
            onChange={(v) => update((c) => ({ ...c, solid: { ...c.solid, yaw_deg: v } }))} />
          <Slider id="solid-pitch" control={PITCH} value={config.solid.pitch_deg}
            onChange={(v) => update((c) => ({ ...c, solid: { ...c.solid, pitch_deg: v } }))} />
        </section>

        <section>
          <h2>Gravity</h2>
          <Slider id="gravity-tilt" control={G_TILT} value={config.gravity.tilt_deg}
            onChange={(v) => update((c) => ({ ...c, gravity: { ...c.gravity, tilt_deg: v } }))} />
          <Slider id="gravity-azimuth" control={G_AZIMUTH} value={config.gravity.azimuth_deg}
            onChange={(v) => update((c) => ({ ...c, gravity: { ...c.gravity, azimuth_deg: v } }))} />
        </section>

        <section>
          <h2>Parameters</h2>
          <ParamPanel
            fields={fields}
            values={config.model}
            onChange={(path, v) => update((c) => ({ ...c, model: { ...withSetting(c.model, path, v), kind: c.model.kind } }))}
          />
        </section>

        <section>
          <h2>Judge the cut as</h2>
          <select
            id="volume-archetype"
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
            <label htmlFor="volume-seed">Seed</label>
            <input
              id="volume-seed"
              type="number"
              min={0}
              value={config.seed}
              onChange={(e) => update((c) => ({ ...c, seed: Math.max(0, Math.floor(Number(e.target.value) || 0)) }))}
            />
          </div>
        </section>
      </aside>

      <main className="viewer">
        <div className="tabs" role="toolbar" aria-label="3D view settings">
          <span className="tab-status muted small" aria-live="polite">
            {cutBusy ? "Updating the cut…" : cut ? `cut ${cut.width}×${cut.height} px · ${cut.elapsed_ms} ms` : ""}
          </span>
          {error === STOPPED && (
            <button
              type="button"
              onClick={() => {
                setError(null);
                setRebuild((n) => n + 1);
              }}
            >
              Rebuild
            </button>
          )}
          <label className="inline small">
            <span className="micro-label">3D view</span>
            <select id="view-resolution" value={viewRes} onChange={(e) => setViewRes(Number(e.target.value))}>
              {VIEW_RESOLUTIONS.map((r) => (
                <option key={r} value={r}>
                  {r}³
                </option>
              ))}
            </select>
          </label>
          <label className="inline small">
            <span className="micro-label">Cut</span>
            <select id="cut-resolution" value={cutRes} onChange={(e) => setCutRes(Number(e.target.value))}>
              {CUT_RESOLUTIONS.map((r) => (
                <option key={r} value={r}>
                  {r} px
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        <div className="volume-panes">
          <Volume3D
            volume={voxels}
            plane={cut?.plane ?? null}
            busy={voxelsBusy}
            progress={
              <TaskProgress
                task={voxelsTask}
                title="Building the 3D view"
                onCancel={cancelBuild}
                onDark
                fallback="Building the 3D view…"
              />
            }
            growth={growth}
            exportRef={view3d}
          />
          {cut && (
            <SlabView
              identity="volume-cut"
              imageSrc={cut.image}
              tdepSrc={cut.tdep}
              dxMm={cut.dx_mm}
              growth={growth}
              stages={cut.stages}
              caption={
                `The cut${cut.pieces > 1 ? ` (largest of ${cut.pieces} pieces)` : ""}` +
                (cut.gravity_in_plane < 0.999 ? ` · gravity ${Math.round(cut.gravity_in_plane * 100)}% in its plane` : "")
              }
            />
          )}
        </div>

        <GrowthControls id="volume" value={growth} onChange={setGrowth} stages={cut?.stages} />
        <ExportAnimation
          name={`${config.name}-growth-3d`}
          source={() => (cutPixels ? captioned(sideBySide(view3d.current, slabSource(cutPixels)), cut?.stages) : null)}
        />

        <section className="cut-controls" aria-label="The cut">
          <div className="toggle" role="group" aria-label="Standard cuts">
            {CUT_VIEWS.map(([label, s]) => (
              <button key={label} type="button" onClick={() => setSlice(s)}>
                {label}
              </button>
            ))}
          </div>
          <Slider id="cut-tilt" control={CUT_TILT} value={config.slice.tilt_deg} onChange={(v) => setSlice({ tilt_deg: v })} />
          <Slider id="cut-azimuth" control={CUT_AZIMUTH} value={config.slice.azimuth_deg}
            onChange={(v) => setSlice({ azimuth_deg: v })} />
          <Slider id="cut-offset" control={OFFSET} value={config.slice.offset_mm} onChange={(v) => setSlice({ offset_mm: v })} />
        </section>

        <CriteriaPanel evaluation={cut?.evaluation ?? null} archetypes={archetypes} />

        <section className="survey" aria-label="Random cuts">
          <h2>Random cuts</h2>
          <p className="muted small">
            A collector sees an agate through whatever cut the saw made. This cuts the run at random planes and
            judges each cut as a slab.
          </p>
          <div className="run-actions">
            <select id="survey-count" value={surveyCount} onChange={(e) => setSurveyCount(Number(e.target.value))}>
              {SURVEY_COUNTS.map((n) => (
                <option key={n} value={n}>
                  {n} cuts
                </option>
              ))}
            </select>
            <button type="button" onClick={runSurvey} disabled={surveyBusy || !config.archetype}>
              {surveyBusy ? "Cutting…" : "Survey random cuts"}
            </button>
            {!config.archetype && <span className="muted small">Choose an archetype to judge the cuts.</span>}
          </div>
          <TaskProgress task={surveyTask} title="Surveying random cuts" onCancel={cancelSurvey} />
          {survey && <SurveyTable result={survey} />}
        </section>

        <StatsPanel columns={[{ title: "The cut", stats: cut?.stats ?? null }]} />

        <section className="run-actions" aria-label="Full 3D run">
          <select id="volume-run-resolution" value={runRes} onChange={(e) => setRunRes(Number(e.target.value))}>
            {RUN_RESOLUTIONS.map((r) => (
              <option key={r} value={r}>
                {r}³ voxels
              </option>
            ))}
          </select>
          <button type="button" className="primary" onClick={startRun} disabled={jobRunning}>
            Save a full 3D run
          </button>
          {job && (
            <span className="small muted" aria-live="polite">
              {job.status === "done"
                ? `Saved to runs/${job.run_id ?? ""}`
                : job.status === "failed"
                  ? job.error === "cancelled"
                    ? "Cancelled"
                    : `Failed: ${job.error ?? ""}`
                  : `${job.status}…`}
            </span>
          )}
          <TaskProgress
            task={jobRunning ? job.id : null}
            title="Saving the full 3D run"
            onCancel={() => job && void progressApi.cancel(job.id)}
          />
        </section>

        <VolumeRuns runs={savedRuns} opening={opening} onOpen={openRun} />
      </main>
    </div>
  );
}

function SurveyTable({ result }: { result: SurveyResult }) {
  const s = result.summary;
  return (
    <div className="survey-result">
      <p>
        <strong>{pct(s.pass_rate)}</strong> of {s.judged} cuts pass as {s.archetype}{" "}
        <span className="muted small">({(result.elapsed_ms / 1000).toFixed(1)} s)</span>
      </p>
      <table className="stats-table">
        <thead>
          <tr>
            <th>Criterion</th>
            <th>Cuts passing</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(s.criteria).map(([id, r]) => (
            <tr key={id}>
              <td>{id}</td>
              <td>{pct(r)}</td>
            </tr>
          ))}
          {s.by_gravity_in_plane.map((b) => (
            <tr key={b.gravity_in_plane.join("-")}>
              <td>
                Gravity {Math.round(b.gravity_in_plane[0] * 100)}–{Math.round(b.gravity_in_plane[1] * 100)}% in the cut
              </td>
              <td>
                {pct(b.pass_rate)} <span className="muted">of {b.cuts}</span>
              </td>
            </tr>
          ))}
          {s.apparent_over_true && (
            <tr>
              <td>Apparent / true band thickness</td>
              <td>
                {s.apparent_over_true.median.toFixed(2)}{" "}
                <span className="muted">
                  ({s.apparent_over_true.q25.toFixed(2)}–{s.apparent_over_true.q75.toFixed(2)})
                </span>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
