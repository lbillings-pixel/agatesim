// Types and calls for the agatesim backend (src/agatesim/server/app.py).

import type { Stage } from "./lib/animation";
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

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
  detailUrl: (name: string) => `${specimenPath(name)}/detail`,
  settings: (name: string) => request<SpecimenSettings>(`${specimenPath(name)}/settings`),
  saveSettings: (name: string, s: SpecimenSettings) =>
    request<SpecimenSettings>(`${specimenPath(name)}/settings`, { method: "PUT", body: JSON.stringify(s) }),
  analyse: (name: string, s: SpecimenSettings) =>
    request<SpecimenAnalysis>(`${specimenPath(name)}/analyse`, { method: "POST", body: JSON.stringify(s) }),
  replicate: (name: string, s: SpecimenSettings) =>
    request<Replica>(`${specimenPath(name)}/replicate`, { method: "POST", body: JSON.stringify(s) }),
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

export interface SurveyResult {
  summary: SurveySummary;
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
}

export const volume = {
  meta: () => request<VolumeMeta>("/api/volume/meta"),
  cut: (config: VolumeConfig, resolution: number, signal?: AbortSignal) =>
    request<CutResult>("/api/volume/cut", {
      method: "POST",
      body: JSON.stringify({ config, resolution }),
      signal,
    }),
  voxels: async (config: VolumeConfig, resolution: number, signal?: AbortSignal): Promise<VoxelVolume> => {
    const response = await fetch("/api/volume/voxels", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config, resolution }),
      signal,
    });
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
  },
  survey: (config: VolumeConfig, cuts: number, resolution: number, signal?: AbortSignal) =>
    request<SurveyResult>("/api/volume/survey", {
      method: "POST",
      body: JSON.stringify({ config, cuts, resolution }),
      signal,
    }),
  startRun: (config: VolumeConfig, surveyCuts: number) =>
    request<Job>("/api/volume/runs", {
      method: "POST",
      body: JSON.stringify({ config, survey_cuts: surveyCuts }),
    }),
  runs: () => request<VolumeRunSummary[]>("/api/volume/runs"),
  run: (id: string) => request<VolumeRunDetail>(`/api/volume/runs/${id}`),
  slabUrl: (id: string) => `/api/volume/runs/${id}/slab.png`,
};

export const api = {
  meta: () => request<Meta>("/api/meta"),
  glossary: () => request<{ markdown: string }>("/api/glossary"),
  preview: (config: RunConfig, resolution: number, signal?: AbortSignal) =>
    request<PreviewResult>("/api/preview", {
      method: "POST",
      body: JSON.stringify({ config, resolution }),
      signal,
    }),
  optics: (
    config: RunConfig,
    resolution: number,
    view: "shadow" | "iris",
    angleDeg: number,
    signal?: AbortSignal,
  ) =>
    request<{ image: string; elapsed_ms: number }>("/api/optics", {
      method: "POST",
      body: JSON.stringify({ config, resolution, view, angle_deg: angleDeg }),
      signal,
    }),
  randomize: (config: RunConfig, strength: number, keepForm: boolean) =>
    request<RandomizeResult>("/api/randomize", {
      method: "POST",
      body: JSON.stringify({ config, strength, keep_form: keepForm }),
    }),
  startRun: (config: RunConfig) =>
    request<Job>("/api/runs", { method: "POST", body: JSON.stringify(config) }),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  slabUrl: (id: string) => `/api/runs/${id}/slab.png`,
  tdepUrl: (id: string) => `/api/runs/${id}/tdep.png`,
};
