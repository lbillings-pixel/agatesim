// Geometry for hand-marked transects: a line across the photo and band
// boundaries marked along it, kept as fractions t in [0, 1] (ADR 0019).

export type Point = [number, number];

export interface Transect {
  start: Point;
  end: Point;
  boundaries: number[];
}

/** The t of the point on the segment nearest to p (clamped to the segment). */
export function project(line: { start: Point; end: Point }, p: Point): number {
  const [x0, y0] = line.start;
  const dx = line.end[0] - x0;
  const dy = line.end[1] - y0;
  const length2 = dx * dx + dy * dy;
  if (length2 === 0) return 0;
  const t = ((p[0] - x0) * dx + (p[1] - y0) * dy) / length2;
  return Math.min(1, Math.max(0, t));
}

/** Distance from p to the segment, in the same units as the points. */
export function distanceTo(line: { start: Point; end: Point }, p: Point): number {
  const [x, y] = at(line, project(line, p));
  return Math.hypot(p[0] - x, p[1] - y);
}

export function at(line: { start: Point; end: Point }, t: number): Point {
  return [line.start[0] + t * (line.end[0] - line.start[0]), line.start[1] + t * (line.end[1] - line.start[1])];
}

/** Index of the mark within `radius` (photo px) of t along the line, or -1. */
export function markNear(line: Transect, t: number, radius: number): number {
  const length = Math.hypot(line.end[0] - line.start[0], line.end[1] - line.start[1]);
  let best = -1;
  let bestDistance = radius;
  line.boundaries.forEach((m, i) => {
    const d = Math.abs(m - t) * length;
    if (d <= bestDistance) {
      best = i;
      bestDistance = d;
    }
  });
  return best;
}

/** Add a mark at t, or remove the one already within `radius` px of it. */
export function toggleMark(line: Transect, t: number, radius: number): Transect {
  const i = markNear(line, t, radius);
  const boundaries =
    i >= 0 ? line.boundaries.filter((_, j) => j !== i) : [...line.boundaries, t].sort((a, b) => a - b);
  return { ...line, boundaries };
}

/** End points of a short tick across the line at t, `half` px each side. */
export function tick(line: { start: Point; end: Point }, t: number, half: number): [Point, Point] {
  const dx = line.end[0] - line.start[0];
  const dy = line.end[1] - line.start[1];
  const length = Math.hypot(dx, dy) || 1;
  const [nx, ny] = [-dy / length, dx / length];
  const [x, y] = at(line, t);
  return [
    [x - half * nx, y - half * ny],
    [x + half * nx, y + half * ny],
  ];
}
