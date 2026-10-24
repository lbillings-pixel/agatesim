// Types and calls for the agatesim backend (src/agatesim/server/app.py).

import type { Stage } from "./lib/animation";
import type { CostEstimate } from "./lib/caution";
import type { Progress } from "./lib/progress";
import type { Transect } from "./lib/transect";

export type Nature = "physical" | "effective" | "imposed";

export interface JsonSchemaProperty {
  type?: string;
  default?: unknown;
  description?: string;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  const?: string;
  enum?: unknown[];
  $ref?: string;
  units?: string;
  nature?: Nature;
  /** The setting matters only when one of these holds (see `isUsed` in lib/schema). */
  used_when?: Record<string, string[]>[];
  /** The bounded range Randomize draws from (ADR 0051). */
  explore?: { min: number; max: number; log: boolean };
  /** One of the model's key settings, shown first. */
  key?: boolean;
}

/** A nested model's schema; `presets` are ready-made values for its settings. */
export interface NestedSchema {
  properties: Record<string, JsonSchemaProperty>;
  presets?: Record<string, Record<string, number>>;
}

/** A pydantic JSON schema: fields, and the nested models they refer to. */
export interface ModelSchema {
  properties: Record<string, JsonSchemaProperty>;
  $defs?: Record<string, NestedSchema>;
}

/** What Randomize may vary besides the key settings. */
export type RandomizeExtra = "cavity" | "schedules" | "order";

/** New settings drawn by Randomize. */
export interface RandomizeResult {
  config: RunConfig;
  attempts: number;
  checked: boolean;
  accepted: boolean;
  note: string;
}

export type ScheduleEvent =
  | { type: "step"; at: number; value: number }
  | { type: "ramp"; start: number; end: number; value: number }
  | { type: "pulse"; at: number; width: number; value: number };

export interface Schedule {
  base: number;
  events: ScheduleEvent[];
}

export interface ScheduledVariable {
  key: string;
  label: string;
  description: string;
  min: number;
  max: number;
  nature: Nature;
  default: Schedule;
}

export interface ModelInfo {
  kind: string;
  title: string;
  schema: ModelSchema;
  schedules: ScheduledVariable[];
}

export interface BandStats {
  band_count: number;
  thickness_mean_mm: number | null;
  thickness_median_mm: number | null;
  thickness_cv: number | null;
  translucency_contrast: number | null;
  iron_mean: number | null;
  chalcedony_fraction: number;
  quartz_fraction: number;
  open_fraction: number;
  crystal_count: number;
}

export type Host = "volcanic" | "sedimentary" | "seam";

export interface CavityInfo {
  name: string;
  host: Host;
  description: string;
  outline: [number, number][];
  corners: number;
}

export interface CriterionInfo {
  id: string;
  description: string;
  pass: string;
}

export interface ArchetypeInfo {
  id: string;
  name: string;
  rung: number;
  status: { procedural: string; mechanistic: string };
  implemented: boolean;
  criteria: CriterionInfo[];
}

export interface RunConfig {
  name: string;
  seed: number;
  archetype?: string | null;
  grid: { resolution: number; margin_fraction: number };
  cavity: CavityConfig;
  model: ModelConfig;
}

/** A thin filament crossing the slab, seen end-on (tube agate). */
export interface Tube {
  x_mm: number;
  y_mm: number;
  radius_mm: number;
}

/** A preset shape, or a drawn outline with its host. Exactly one of preset and outline. */
export interface CavityConfig {
  preset?: string | null;
  outline?: [number, number][] | null;
  host?: Host | null;
  smooth?: boolean;
  size_mm: number;
  rotation_deg: number;
  tubes?: Tube[];
}

export type ModelConfig = { kind: string; schedules?: Record<string, Schedule> } & Record<string, unknown>;

export interface Meta {
  version: string;
  limits: { preview: number; run: number };
  /** Whether H2 (Liesegang) runs on the GPU; on the CPU it takes many minutes. */
  gpu: boolean;
  cavities: CavityInfo[];
  models: ModelInfo[];
  /** description: the preset file's header comment, in prose. */
  presets: { name: string; config: RunConfig; description: string }[];
  archetypes: ArchetypeInfo[];
}

export interface CriterionResult {
  id: string;
  value: number | null;
  min: number | null;
  max: number | null;
  passed: boolean;
  detail: string;
}

export interface Evaluation {
  archetype: string;
  passed: boolean;
  criteria: CriterionResult[];
}

export interface PreviewResult {
  image: string;
  tdep: string;
  width: number;
  height: number;
  dx_mm: number;
  x0_mm: number;
  y1_mm: number;
  elapsed_ms: number;
  evaluation: Evaluation | null;
  stats: BandStats;
  stages?: Stage[];
}

export interface Job {
  id: string;
  name: string;
  status: "queued" | "running" | "done" | "failed";
  submitted_utc: string;
  run_id: string | null;
  error: string | null;
}

export interface RunSummary {
  id: string;
  name: string;
  started_utc: string;
  elapsed_s: number;
  cavity: string;
  model: string;
  archetype: string | null;
  passed: boolean | null;
  nx: number;
  ny: number;
}

export interface RunDetail {
  id: string;
  config: RunConfig;
  metadata: { grid: { nx: number; ny: number; dx_mm: number }; git: { commit: string | null } };
  evaluation: Evaluation | null;
  stats: BandStats | null;
  stages?: Stage[];
}

async function request<T>(path: string, init?: RequestInit, task?: string): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...taskHeaders(task, init?.signal), ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

/** The header that names a long request's task (its progress is read under that
 * id), and a cancel sent to the server if the request is abandoned, so the work
 * stops there too (src/agatesim/server/tasks.py). */
function taskHeaders(task: string | undefined, signal: AbortSignal | null | undefined): Record<string, string> {
  if (!task) return {};
  signal?.addEventListener("abort", () => void progress.cancel(task), { once: true });
  return { "X-Progress": task };
}

export const progress = {
  /** How far a task has got; null if the server hasn't started it yet. */
  get: async (task: string): Promise<Progress | null> => {
    const response = await fetch(`/api/progress/${encodeURIComponent(task)}`);
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(await errorMessage(response));
    return (await response.json()) as Progress;
  },
  cancel: async (task: string): Promise<void> => {
    await fetch(`/api/progress/${encodeURIComponent(task)}`, { method: "DELETE" }).catch(() => undefined);
  },
};

/** Turn a FastAPI error (often a list of validation errors) into one readable line. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg ?? ""}`)
        .join("; ");
    }
  } catch {
    // fall through
  }
  return `${response.status} ${response.statusText}`;
}

export interface SpecimenFile {
  name: string;
  bytes: number;
  has_settings: boolean;
  badges: QualityBadge[] | null; // null until the photo has been scored
}

export type QualityLevel = "fit" | "borderline" | "not fit";

export interface QualityReason {
  score: string;
  level: QualityLevel;
  message: string;
  advice: string;
}

export interface QualityBadge {
  use: "classification" | "calibration";
  level: QualityLevel;
  reasons: QualityReason[];
}

/** Measured scores of a photo's cut face (src/agatesim/specimen/quality.py). */
export interface PhotoQuality {
  face_px: number;
  band_spacing_px: number | null;
  band_contrast: number | null;
  contrast_to_noise: number | null;
  fine_detail: number | null;
  edge_width_px: number | null;
  resolution_mm: number | null;
  noise: number;
  blocking: number;
  clipped: number;
  cast: number | null;
  cast_hue: string | null;
  mm_per_px: number | null;
  profiles_used: number;
}

export interface SpecimenSettings {
  calibration: {
    p1: [number, number];
    p2: [number, number];
    distance_mm: number;
    face_height_mm: number;
  } | null;
  host: Host;
  up_deg: number;
  seed: [number, number] | null;
  transects: Transect[];
}

export interface TransectScore {
  marked: number;
  traced: number;
  matched: number;
  missed: number;
  extra: number;
  precision: number | null;
  recall: number | null;
  mean_offset_mm: number | null;
  tolerance_mm: number;
  chance_recall: number | null;
}

export interface IdentifiedForm {
  archetype: string;
  passed: boolean;
  verdict: string;
  pass_reliable: boolean;
  detection_rate: number | null;
  score: number;
  criteria: CriterionResult[];
}

export interface SpecimenAnalysis {
  mm_per_px: number;
  camera_height_mm: number | null;
  outline_px: [number, number][];
  size_mm: number;
  outline_mm: [number, number][];
  host: Host;
  band_map: string;
  stats: BandStats;
  identification: IdentifiedForm[];
  not_from_photos: Record<string, string>;
  transects: { traced: number[]; score: TransectScore; edges: number[]; edge_score: TransectScore }[];
}

export interface Replica {
  config: RunConfig;
  image: string;
  stats: BandStats;
  target: BandStats;
  mismatch: number;
}

const specimenPath = (name: string) => `/api/specimens/${encodeURIComponent(name)}`;

export const specimens = {
  list: () => request<SpecimenFile[]>("/api/specimens"),
  upload: async (file: File) => {
    const response = await fetch(`/api/specimens?name=${encodeURIComponent(file.name)}`, {
      method: "POST",
      body: file,
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    return (await response.json()) as { name: string };
  },
  photoUrl: (name: string) => `${specimenPath(name)}/photo`,
  thumbUrl: (name: string) => `${specimenPath(name)}/thumb`,
  rename: (name: string, to: string) =>
    request<{ name: string }>(`${specimenPath(name)}/rename`, { method: "POST", body: JSON.stringify({ to }) }),
  remove: (name: string) => request<{ deleted: string; kept_in: string }>(specimenPath(name), { method: "DELETE" }),
  quality: (name: string, s: SpecimenSettings) =>
    request<{ quality: PhotoQuality; badges: QualityBadge[] }>(`${specimenPath(name)}/quality`, {
      method: "POST",
      body: JSON.stringify(s),
    }),
  detailUrl: (name: string) => `${specimenPath(name)}/detail`,
  settings: (name: string) => request<SpecimenSettings>(`${specimenPath(name)}/settings`),
  saveSettings: (name: string, s: SpecimenSettings) =>
    request<SpecimenSettings>(`${specimenPath(name)}/settings`, { method: "PUT", body: JSON.stringify(s) }),
  analyse: (name: string, s: SpecimenSettings) =>
    request<SpecimenAnalysis>(`${specimenPath(name)}/analyse`, { method: "POST", body: JSON.stringify(s) }),
  replicate: (name: string, s: SpecimenSettings) =>
    request<Replica>(`${specimenPath(name)}/replicate`, { method: "POST", body: JSON.stringify(s) }),
  classify: (name: string) => request<ClassifierAnswer>(`${specimenPath(name)}/classify`, { method: "POST" }),
  /** Rough locations of features whose map passed the tap test (ADR 0068). */
  maps: (name: string) => request<FeatureMapAnswer>(`${specimenPath(name)}/maps`, { method: "POST" }),
  /** The owner's label of their own photo, kept beside it (never in the library). */
  label: (name: string) => request<LibraryLabel | null>(`${specimenPath(name)}/label`),
  saveLabel: (name: string, label: LibraryLabel) =>
    request<LibraryLabel>(`${specimenPath(name)}/label`, { method: "PUT", body: JSON.stringify(label) }),
  clearLabel: async (name: string) => {
    const response = await fetch(`${specimenPath(name)}/label`, { method: "DELETE" });
    if (!response.ok) throw new Error(await errorMessage(response));
  },
};

/** Feature maps on a photo (src/agatesim/maps.py, ADR 0068): per-patch
 * probabilities in rows of the photo from its top, appearance only. */
export interface FeatureMapAnswer {
  ready: boolean;
  why?: string;
  maps?: { feature: string; grid: number[][]; score: number; centre: number }[];
  not_shown?: { feature: string; photos: number; score: number }[];
}

/** The learned form classifier's answer on a photo (ADR 0067): appearance only. */
export interface ClassifierAnswer {
  ready: boolean;
  /** Why there is no answer yet. */
  why?: string;
  /** Forms at or above the threshold, most likely first; empty: undetermined. */
  likely?: { form: string; p: number }[];
  ranked?: { form: string; p: number }[];
  /** Labelled photos of each form it was trained on. */
  trained_on?: Record<string, number>;
  threshold?: number;
}

export interface ClassifierStatus {
  model: boolean;
  trained: boolean;
  own_labels: number;
  training: boolean;
  estimate?: CostEstimate;
}

export const classifier = {
  status: () => request<ClassifierStatus>("/api/classifier"),
  train: (task: string) =>
    request<{ photos: number; own_photos: number; simulated: number }>(
      "/api/classifier/train",
      { method: "POST" },
      task,
    ),
};

/** A reference-library photo's labels (src/agatesim/library.py, ADR 0066). */
export interface LibraryLabel {
  verdict: "forms" | "cant-tell" | "unusable";
  forms: string[];
  sure: boolean;
  features: string[];
  note: string;
}

export interface LibraryImage {
  id: string;
  title: string;
  source: string;
  author: string;
  licence: string;
  licence_url: string;
  guesses: string[];
  fetched: boolean;
  label: LibraryLabel | null;
}

export interface LibraryIndex {
  forms: { id: string; name: string }[];
  features: string[];
  images: LibraryImage[];
}

/** Test taps on one held-out photo (src/agatesim/taps.py, ADR 0068): points
 * as [x, y] fractions of the photo from its top left. */
export interface FeatureTaps {
  inside: [number, number][];
  outside: [number, number][];
}

export interface TapPhoto {
  id: string;
  targets: string[];
  taps: Record<string, FeatureTaps>;
  done: boolean;
}

export const library = {
  list: () => request<LibraryIndex>("/api/library"),
  taps: () => request<{ photos: TapPhoto[] }>("/api/library/taps"),
  saveTaps: (id: string, taps: Record<string, FeatureTaps>) =>
    request<{ taps: Record<string, FeatureTaps>; done: boolean }>(
      `/api/library/${encodeURIComponent(id)}/taps`,
      { method: "PUT", body: JSON.stringify(taps) },
    ),
  imageUrl: (id: string) => `/api/library/${encodeURIComponent(id)}/image`,
  label: (id: string, label: LibraryLabel) =>
    request<LibraryLabel>(`/api/library/${encodeURIComponent(id)}/label`, {
      method: "PUT",
      body: JSON.stringify(label),
    }),
  clear: async (id: string) => {
    const response = await fetch(`/api/library/${encodeURIComponent(id)}/label`, { method: "DELETE" });
    if (!response.ok) throw new Error(await errorMessage(response));
  },
};

// --- 3D runs (src/agatesim/server/volume.py) ---

export interface SolidConfig {
  preset?: string | null;
  outline?: [number, number][] | null;
  host?: Host | null;
  smooth?: boolean;
  depth_fraction?: number;
  size_mm: number;
  yaw_deg: number;
  pitch_deg: number;
}

export interface SliceConfig {
  tilt_deg: number;
  azimuth_deg: number;
  offset_mm: number;
  resolution: number;
}

export interface VolumeConfig {
  name: string;
  seed: number;
  archetype?: string | null;
  grid: { resolution: number; margin_fraction: number };
  solid: SolidConfig;
  gravity: { tilt_deg: number; azimuth_deg: number };
  model: ModelConfig;
  slice: SliceConfig;
}

export interface VolumeMeta {
  solids: { name: string; host: Host; description: string }[];
  presets: { name: string; config: VolumeConfig }[];
  kinds: string[];
  limits: { cut: number; view: number; survey: number; run: number };
}

export interface CutPlane {
  origin: [number, number, number];
  u: [number, number, number];
  v: [number, number, number];
  normal: [number, number, number];
}

export interface CutResult extends PreviewResult {
  plane: CutPlane;
  pieces: number;
  gravity_in_plane: number;
}

export interface VoxelVolume {
  nx: number;
  ny: number;
  nz: number;
  dx_mm: number;
  origin_mm: [number, number, number];
  elapsed_ms: number;
  rgba: Uint8Array;
  /** Deposition time per voxel (0..254 = time 0..1, 255 = never), for the growth animation. */
  tdep: Uint8Array | null;
  /** For a saved run's view: every stride-th voxel of the run along each axis. */
  stride?: number;
}

export interface SurveySummary {
  archetype: string | null;
  cuts: number;
  judged: number;
  pass_rate: number | null;
  criteria: Record<string, number | null>;
  by_gravity_in_plane: { gravity_in_plane: [number, number]; cuts: number; pass_rate: number | null }[];
  true_thickness_mm: number | null;
  apparent_over_true?: { q25: number; median: number; q75: number };
}

/** One random cut of a survey: where it was made, its verdict and a small picture. */
export interface SurveyCut {
  tilt_deg: number;
  azimuth_deg: number;
  offset_mm: number;
  pieces: number;
  gravity_in_plane: number | null;
  passed: boolean | null;
  criteria: Record<string, boolean>;
  error: string | null;
  thumbnail?: string | null;
}

export interface SurveyResult {
  summary: SurveySummary;
  cuts: SurveyCut[];
  elapsed_ms: number;
}

export interface VolumeRunSummary {
  id: string;
  name: string;
  started_utc: string;
  elapsed_s: number;
  solid: string;
  model: string;
  archetype: string | null;
  passed: boolean | null;
  survey: { cuts: number; pass_rate: number | null } | null;
  grid: { nx: number; ny: number; nz: number; dx_mm: number };
}

export interface VolumeRunDetail {
  summary: VolumeRunSummary;
  config: VolumeConfig;
  metrics: Evaluation | null;
  survey: { summary: SurveySummary; cuts: SurveyCut[] } | null;
}

/** Voxel colours and deposition times, as the server sends them (an X-Volume header, then bytes). */
async function readVoxels(response: Response): Promise<VoxelVolume> {
  if (!response.ok) throw new Error(await errorMessage(response));
  const header = JSON.parse(response.headers.get("X-Volume") ?? "{}") as Omit<VoxelVolume, "rgba" | "tdep"> & {
    tdep?: boolean;
  };
  const bytes = new Uint8Array(await response.arrayBuffer());
  const n = header.nx * header.ny * header.nz;
  return {
    ...header,
    rgba: bytes.subarray(0, 4 * n),
    tdep: header.tdep ? bytes.subarray(4 * n, 5 * n) : null,
  };
}

export const volume = {
  meta: () => request<VolumeMeta>("/api/volume/meta"),
  cut: (config: VolumeConfig, resolution: number, signal?: AbortSignal, task?: string) =>
    request<CutResult>(
      "/api/volume/cut",
      {
        method: "POST",
        body: JSON.stringify({ config, resolution }),
        signal,
      },
      task,
    ),
  voxels: async (
    config: VolumeConfig,
    resolution: number,
    signal?: AbortSignal,
    task?: string,
  ): Promise<VoxelVolume> =>
    readVoxels(
      await fetch("/api/volume/voxels", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...taskHeaders(task, signal) },
        body: JSON.stringify({ config, resolution }),
        signal,
      }),
    ),
  /** A saved run's own volume, read from its files (every stride-th voxel of a large one). */
  runVoxels: async (id: string, signal?: AbortSignal): Promise<VoxelVolume> =>
    readVoxels(await fetch(`/api/volume/runs/${encodeURIComponent(id)}/voxels`, { signal })),
  survey: (config: VolumeConfig, cuts: number, resolution: number, signal?: AbortSignal, task?: string) =>
    request<SurveyResult>(
      "/api/volume/survey",
      {
        method: "POST",
        body: JSON.stringify({ config, cuts, resolution }),
        signal,
      },
      task,
    ),
  startRun: (config: VolumeConfig, surveyCuts: number) =>
    request<Job>("/api/volume/runs", {
      method: "POST",
      body: JSON.stringify({ config, survey_cuts: surveyCuts }),
    }),
  runs: () => request<VolumeRunSummary[]>("/api/volume/runs"),
  /** Rough time and memory of building the view, a survey and a full run (the caution badge). */
  estimate: (
    config: VolumeConfig,
    sizes: { view: number; cut: number; surveyCuts: number; run: number; runSurveyCuts: number },
    signal?: AbortSignal,
  ) =>
    request<{ view: CostEstimate; survey: CostEstimate; run: CostEstimate }>("/api/volume/estimate", {
      method: "POST",
      body: JSON.stringify({
        config,
        view_resolution: sizes.view,
        cut_resolution: sizes.cut,
        survey_cuts: sizes.surveyCuts,
        run_resolution: sizes.run,
        run_survey_cuts: sizes.runSurveyCuts,
      }),
      signal,
    }),
  run: (id: string) => request<VolumeRunDetail>(`/api/volume/runs/${id}`),
  slabUrl: (id: string) => `/api/volume/runs/${id}/slab.png`,
};

export const api = {
  meta: () => request<Meta>("/api/meta"),
  glossary: () => request<{ markdown: string }>("/api/glossary"),
  preview: (config: RunConfig, resolution: number, signal?: AbortSignal, task?: string) =>
    request<PreviewResult>(
      "/api/preview",
      {
        method: "POST",
        body: JSON.stringify({ config, resolution }),
        signal,
      },
      task,
    ),
  optics: (
    config: RunConfig,
    resolution: number,
    view: "shadow" | "iris",
    angleDeg: number,
    azimuthDeg: number,
    signal?: AbortSignal,
    task?: string,
  ) =>
    request<{ image: string; elapsed_ms: number; note: string }>(
      "/api/optics",
      {
        method: "POST",
        body: JSON.stringify({ config, resolution, view, angle_deg: angleDeg, azimuth_deg: azimuthDeg }),
        signal,
      },
      task,
    ),
  randomize: (
    config: RunConfig,
    strength: number,
    keepForm: boolean,
    extras: RandomizeExtra[],
    signal?: AbortSignal,
    task?: string,
  ) =>
    request<RandomizeResult>(
      "/api/randomize",
      {
        method: "POST",
        body: JSON.stringify({ config, strength, keep_form: keepForm, extras }),
        signal,
      },
      task,
    ),
  startRun: (config: RunConfig) =>
    request<Job>("/api/runs", { method: "POST", body: JSON.stringify(config) }),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  /** Delete a saved run, 2D or 3D. */
  deleteRun: async (id: string): Promise<void> => {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!response.ok) throw new Error(await errorMessage(response));
  },
  /** Rough time and memory of the preview and of a full run (the caution badge). */
  estimate: (config: RunConfig, previewResolution: number, runResolution: number, signal?: AbortSignal) =>
    request<{ preview: CostEstimate; run: CostEstimate }>("/api/estimate", {
      method: "POST",
      body: JSON.stringify({ config, preview_resolution: previewResolution, run_resolution: runResolution }),
      signal,
    }),
  /** Saved runs (2D and 3D) and the bytes they take on disk. */
  runsUsage: () => request<{ runs: number; bytes: number }>("/api/runs-usage"),
  slabUrl: (id: string) => `/api/runs/${id}/slab.png`,
  tdepUrl: (id: string) => `/api/runs/${id}/tdep.png`,
};
