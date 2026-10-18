// Forms and their verification presets: `<id>` (procedural tier) and
// `<id>-mechanistic` (mechanistic tier), the naming the tests enforce.

import type { ArchetypeInfo, Meta } from "../api";

export type Preset = Meta["presets"][number];
export type Tier = "procedural" | "mechanistic";

export interface FormPair {
  archetype: ArchetypeInfo;
  procedural: Preset | null;
  mechanistic: Preset | null;
}

/** Each implemented form with its verification presets. */
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

/** The forms the form chooser offers: id, name and a preset for each tier. */
export function formPresets(meta: Pick<Meta, "presets" | "archetypes">) {
  return formPairs(meta).map((p) => ({
    id: p.archetype.id,
    name: p.archetype.name,
    procedural: p.procedural,
    mechanistic: p.mechanistic,
  }));
}

/** Presets that aren't a form's verification preset (extra demonstrations). */
export function otherPresets(meta: Pick<Meta, "presets" | "archetypes">): Preset[] {
  const verification = new Set(
    formPairs(meta).flatMap((p) => [p.procedural?.name, p.mechanistic?.name].filter(Boolean)),
  );
  return meta.presets.filter((p) => !verification.has(p.name));
}

/** A model's tier, from its kind. */
export function tierOf(kind: string): Tier {
  return kind.startsWith("mechanistic-") ? "mechanistic" : "procedural";
}
