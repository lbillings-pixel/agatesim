// Orbit camera and ray geometry for the 3D view (world coordinates in mm, z up).

export type Vec3 = [number, number, number];

export interface Orbit {
  yaw: number; // radians, anticlockwise from +x, seen from above
  pitch: number; // radians above the horizontal
  distance: number; // mm from the target
}

export interface Camera {
  eye: Vec3;
  forward: Vec3;
  right: Vec3;
  up: Vec3;
}

export const MAX_PITCH = 1.5;

export const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const scale = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k];
export const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
export const normalize = (a: Vec3): Vec3 => scale(a, 1 / Math.hypot(a[0], a[1], a[2]));

/** The camera looking at `target` from the orbit's direction. */
export function camera(orbit: Orbit, target: Vec3): Camera {
  const { yaw, pitch, distance } = orbit;
  const back: Vec3 = [Math.cos(pitch) * Math.cos(yaw), Math.cos(pitch) * Math.sin(yaw), Math.sin(pitch)];
  const eye = add(target, scale(back, distance));
  const forward = scale(back, -1);
  const right = normalize(cross(forward, [0, 0, 1]));
  return { eye, forward, right, up: cross(right, forward) };
}

/** The orbit that looks straight at a face whose outward normal is `normal`, from a
 * little above. */
export function facing(normal: Vec3, distance: number, lift = 0.35): Orbit {
  const yaw = Math.atan2(normal[1], normal[0]);
  const flat = Math.hypot(normal[0], normal[1]);
  const pitch = flat < 1e-6 ? Math.sign(normal[2]) * MAX_PITCH : Math.atan2(normal[2], flat) + lift;
  return { yaw, pitch: clampPitch(pitch), distance };
}

export const clampPitch = (p: number) => Math.max(-MAX_PITCH, Math.min(MAX_PITCH, p));

/** Where a ray (origin + t dir, t ≥ 0) is inside the box lo..hi, or null. */
export function rayBox(origin: Vec3, dir: Vec3, lo: Vec3, hi: Vec3): [number, number] | null {
  let near = 0;
  let far = Infinity;
  const axes = [0, 1, 2].map((i) => [origin[i], dir[i], lo[i], hi[i]] as [number, number, number, number]);
  for (const [o, d, l, h] of axes) {
    if (Math.abs(d) < 1e-12) {
      if (o < l || o > h) return null;
      continue;
    }
    const a = (l - o) / d;
    const b = (h - o) / d;
    near = Math.max(near, Math.min(a, b));
    far = Math.min(far, Math.max(a, b));
  }
  return far > near ? [near, far] : null;
}

/** The part of a ray segment [near, far] on the kept side of a cut, where the
 * kept side is dot(normal, p) ≤ offset; null if none. `atCut` says the segment
 * starts on the cut face itself. */
export function keptSegment(
  origin: Vec3,
  dir: Vec3,
  near: number,
  far: number,
  normal: Vec3,
  offset: number,
): { near: number; far: number; atCut: boolean } | null {
  const rate = dot(normal, dir);
  const start = dot(normal, origin) - offset;
  let atCut = false;
  if (Math.abs(rate) < 1e-12) {
    if (start > 0) return null;
  } else {
    const t = -start / rate;
    if (rate > 0) far = Math.min(far, t);
    else if (t > near) {
      near = t;
      atCut = true;
    }
  }
  return far > near ? { near, far, atCut } : null;
}
