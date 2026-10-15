// Drawn cavity outlines. `outlineProblem` and `chaikin` mirror
// agatesim.geometry (outline_problem, chaikin); both are pinned to
// tests/fixtures/outlines.json.

export type Point = [number, number];

export const MIN_POINTS = 3;
export const MAX_POINTS = 2000;
export const SMOOTH_ITERATIONS = 4;

function dedupe(points: Point[]): Point[] {
  return points.filter((p, i) => {
    const q = points[(i - 1 + points.length) % points.length];
    return q !== undefined && Math.hypot(p[0] - q[0], p[1] - q[1]) > 1e-12;
  });
}

function signedArea(v: Point[]): number {
  let s = 0;
  v.forEach(([x, y], i) => {
    const [nx, ny] = v[(i + 1) % v.length] ?? [x, y];
    s += x * ny - nx * y;
  });
  return s / 2;
}

function orient(a: Point, b: Point, c: Point): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function onSegment(a: Point, b: Point, c: Point, d: number): boolean {
  const within = (k: 0 | 1) => c[k] >= Math.min(a[k], b[k]) - 1e-12 && c[k] <= Math.max(a[k], b[k]) + 1e-12;
  return Math.abs(d) < 1e-12 && within(0) && within(1);
}

function segmentsCross(p: Point, q: Point, r: Point, s: Point): boolean {
  const d1 = orient(r, s, p);
  const d2 = orient(r, s, q);
  const d3 = orient(p, q, r);
  const d4 = orient(p, q, s);
  if (d1 * d2 < 0 && d3 * d4 < 0) return true;
  return onSegment(r, s, p, d1) || onSegment(r, s, q, d2) || onSegment(p, q, r, d3) || onSegment(p, q, s, d4);
}

/** Why `points` can't bound a cavity, or null if it can (same wording as the backend). */
export function outlineProblem(points: Point[]): string | null {
  const v = dedupe(points);
  const n = v.length;
  if (n < MIN_POINTS) return `needs at least ${MIN_POINTS} distinct points`;
  const xs = v.map((p) => p[0]);
  const ys = v.map((p) => p[1]);
  const extent = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
  if (extent === 0) return "encloses no area";
  for (let i = 0; i < n; i++) {
    const a = v[i];
    const b = v[(i + 1) % n];
    if (!a || !b) continue;
    for (let j = i + 2; j < (i > 0 ? n : n - 1); j++) {
      const c = v[j];
      const d = v[(j + 1) % n];
      if (c && d && segmentsCross(a, b, c, d)) return "crosses itself";
    }
  }
  if (Math.abs(signedArea(v)) < 1e-6 * extent * extent) return "encloses no area";
  return null;
}

/** Chaikin corner cutting of a closed polygon, as the backend smooths outlines. */
export function chaikin(points: Point[], iterations = SMOOTH_ITERATIONS): Point[] {
  let v = points;
  for (let k = 0; k < iterations; k++) {
    v = v.flatMap(([x, y], i) => {
      const [nx, ny] = v[(i + 1) % v.length] ?? [x, y];
      return [
        [0.75 * x + 0.25 * nx, 0.75 * y + 0.25 * ny],
        [0.25 * x + 0.75 * nx, 0.25 * y + 0.75 * ny],
      ] as Point[];
    });
  }
  return v;
}

function perpendicular(p: Point, a: Point, b: Point): number {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  if (len === 0) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  return Math.abs(orient(a, b, p)) / len;
}

/** Ramer–Douglas–Peucker simplification of an open polyline: keeps sharp corners. */
export function simplify(points: Point[], tolerance: number): Point[] {
  if (points.length <= 2) return points;
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) return points;
  let worst = 0;
  let index = 0;
  for (let i = 1; i < points.length - 1; i++) {
    const p = points[i];
    if (!p) continue;
    const d = perpendicular(p, first, last);
    if (d > worst) {
      worst = d;
      index = i;
    }
  }
  if (worst <= tolerance) return [first, last];
  const left = simplify(points.slice(0, index + 1), tolerance);
  return [...left.slice(0, -1), ...simplify(points.slice(index), tolerance)];
}

/** A freehand stroke as a closed outline: simplified, without the closing duplicate. */
export function strokeToOutline(stroke: Point[], tolerance: number): Point[] {
  const first = stroke[0];
  if (!first) return [];
  const closed = simplify([...stroke, first], tolerance);
  return closed.slice(0, -1);
}

/** Scale and centre an outline into a box of side `size` (for thumbnails). */
export function fitToBox(points: Point[], size: number): Point[] {
  if (points.length === 0) return points;
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const k = size / (Math.max(x1 - x0, y1 - y0) || 1);
  return points.map(([x, y]) => [(x - (x0 + x1) / 2) * k, (y - (y0 + y1) / 2) * k]);
}
