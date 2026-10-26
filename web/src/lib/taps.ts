import type { FeatureTaps, TapPhoto } from "../api";

/** Outside points a feature needs before its photo counts as tapped; one
 * inside point is enough, since a small feature may fit only one or two
 * (ENOUGH in src/agatesim/taps.py, ADR 0071). */
export const ENOUGH = 3;

export type Kind = "inside" | "outside";

/** What a tap does: add a point of a kind, or remove one. Removing is its own
 * tool, so taps close together on a small feature never undo each other. */
export type Tool = Kind | "remove";

/** A removing tap takes the active feature's point nearest it, if one is
 * closer than this (as a fraction of the photo's width). */
export const NEAR = 0.025;

export function featureTaps(
  taps: Record<string, FeatureTaps>,
  feature: string,
): FeatureTaps {
  return taps[feature] ?? { inside: [], outside: [] };
}

/** Add a point of `tool`'s kind at (x, y), or with "remove", remove the
 * active feature's point nearest it if one is within NEAR (`aspect` is
 * height / width). */
export function tap(
  taps: Record<string, FeatureTaps>,
  feature: string,
  tool: Tool,
  x: number,
  y: number,
  aspect = 1,
): Record<string, FeatureTaps> {
  const t = featureTaps(taps, feature);
  if (tool !== "remove") {
    const point: [number, number] = [
      Math.min(1, Math.max(0, x)),
      Math.min(1, Math.max(0, y)),
    ];
    return { ...taps, [feature]: { ...t, [tool]: [...t[tool], point] } };
  }
  const dist = ([px, py]: [number, number]) =>
    Math.hypot(px - x, (py - y) * aspect);
  let best: { kind: Kind; i: number; d: number } | null = null;
  for (const k of ["inside", "outside"] as const)
    for (const [i, p] of t[k].entries()) {
      const d = dist(p);
      if (d < NEAR && (best === null || d < best.d)) best = { kind: k, i, d };
    }
  if (!best) return taps;
  const { kind: k, i: drop } = best;
  return {
    ...taps,
    [feature]: { ...t, [k]: t[k].filter((_, i) => i !== drop) },
  };
}

export function enough(t: FeatureTaps): boolean {
  return t.inside.length >= 1 && t.outside.length >= ENOUGH;
}

export function photoDone(
  photo: TapPhoto,
  taps: Record<string, FeatureTaps>,
): boolean {
  return (
    photo.targets.length > 0 &&
    photo.targets.every((f) => enough(featureTaps(taps, f)))
  );
}

/** The next photo after `from` (wrapping round) not yet tapped; null if all are. */
export function nextUndone(
  photos: TapPhoto[],
  from: number,
  step = 1,
): number | null {
  const n = photos.length;
  for (let k = 1; k <= n; k++) {
    const i = (((from + step * k) % n) + n) % n;
    const p = photos[i];
    if (p && !p.done && p.targets.length > 0) return i;
  }
  return null;
}
