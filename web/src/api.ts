// Types and calls for the agatesim backend (src/agatesim/server/app.py).

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
  units?: string;
  nature?: Nature;
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
  schema: { properties: Record<string, JsonSchemaProperty> };
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

export interface CavityInfo {
  name: string;
  host: "volcanic" | "sedimentary" | "seam";
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
  cavity: { preset: string; size_mm: number; rotation_deg: number };
  model: ModelConfig;
}

export type ModelConfig = { kind: string; schedules?: Record<string, Schedule> } & Record<string, unknown>;

export interface Meta {
  version: string;
  limits: { preview: number; run: number };
  cavities: CavityInfo[];
  models: ModelInfo[];
  presets: { name: string; config: RunConfig }[];
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
  elapsed_ms: number;
  evaluation: Evaluation | null;
  stats: BandStats;
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

export const api = {
  meta: () => request<Meta>("/api/meta"),
  preview: (config: RunConfig, resolution: number, signal?: AbortSignal) =>
    request<PreviewResult>("/api/preview", {
      method: "POST",
      body: JSON.stringify({ config, resolution }),
      signal,
    }),
  startRun: (config: RunConfig) =>
    request<Job>("/api/runs", { method: "POST", body: JSON.stringify(config) }),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  slabUrl: (id: string) => `/api/runs/${id}/slab.png`,
  tdepUrl: (id: string) => `/api/runs/${id}/tdep.png`,
};
