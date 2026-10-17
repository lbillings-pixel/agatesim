"""Chemical-garden tubes in 3D (ADR 0047), the counterpart of agatesim.models.gardens.

The tubes grow as in 2D (ADR 0044): seeds on the cavity floor, tips advancing
in short steps, buoyancy turning them back toward vertical, sideways wander,
side tubes where membranes rupture, a shared budget of solution per seed, and
tips stopping at the wall or at another seed's tube. In 3D:

- seeds are sites on the growth surface (the fixed reference lattice, as for
  every 3D stage) whose inward normal is within 60° of up;
- a tip's direction turns toward up by an angle buoyancy × step × its angle
  from vertical, and wanders in both directions across it; a side tube leaves
  at 35° in a random direction about the tube;
- a seed's solution builds the same length of tube as in 2D (`volume_mm2` is
  the area a slab shows, 2 × radius × length);
- tubes are drawn at least DRAWN_RADIUS_MM thick, so voxels and cuts resolve
  them, as branched inclusions are drawn as balls a lattice cell wide.

Every draw is made in world coordinates, so the tubes don't depend on the
resolution of a volume or cut.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from agatesim import _scipy
from agatesim.grid import FloatArray
from agatesim.models.gardens import (
    BRANCH_TURN_DEG,
    FLOOR_COS,
    MAX_STEPS,
    STEP_MM,
    GardenStage,
)
from agatesim.volume.growth import GrowthSolid, place_sites
from agatesim.volume.models import Setting

DRAWN_RADIUS_MM = 0.2  # tubes are drawn at least this thick in 3D
NEAREST_SEGMENTS = 8  # segments compared per point


@dataclass(frozen=True, eq=False)
class Garden3:
    """Tube centrelines as segments, each with its growth order in [0, 1]."""

    a: FloatArray  # (n, 3)
    b: FloatArray  # (n, 3)
    order: FloatArray  # (n,)
    radius: float

    def _segment_distance(self, points: FloatArray) -> tuple[FloatArray, FloatArray]:
        """Distance from each point to the nearest tube centreline, and the
        earliest order among the segments within a radius of it (inf if none)."""
        n = len(points)
        if not len(self.order) or not n:
            return np.full(n, np.inf), np.full(n, np.inf)
        mid = (self.a + self.b) / 2
        k = min(NEAREST_SEGMENTS, len(self.order))
        _, idx = _scipy.NearestIndex(mid).query_k(points, k)
        a, b = self.a[idx], self.b[idx]
        ab = b - a
        t = np.clip(
            np.sum((points[:, None, :] - a) * ab, axis=2)
            / np.maximum(np.sum(ab * ab, axis=2), 1e-12),
            0.0,
            1.0,
        )
        d = np.linalg.norm(points[:, None, :] - (a + t[..., None] * ab), axis=2)
        order = np.where(d <= self.radius, self.order[idx], np.inf).min(axis=1)
        return d.min(axis=1), order

    def order_at(self, points: FloatArray) -> FloatArray:
        """Growth order of the tube at each point; inf outside the tubes."""
        return self._segment_distance(points)[1]

    def distance(self, points: FloatArray) -> FloatArray:
        """Distance from points to the tubes' surface; negative inside them."""
        return self._segment_distance(points)[0] - self.radius


def _turn_toward(direction: FloatArray, target: FloatArray, angle: float) -> FloatArray:
    """Turn a unit vector toward a unit target by `angle` (radians), not past it."""
    cos = float(np.clip(direction @ target, -1.0, 1.0))
    between = math.acos(cos)
    if between < 1e-9:
        return direction
    across = target - cos * direction
    norm = float(np.linalg.norm(across))
    if norm < 1e-12:  # pointing straight away: any perpendicular will do
        across = np.cross(direction, [1.0, 0.0, 0.0])
        if float(np.linalg.norm(across)) < 1e-6:
            across = np.cross(direction, [0.0, 1.0, 0.0])
        norm = float(np.linalg.norm(across))
    across = across / norm
    turn = min(angle, between)
    return np.asarray(math.cos(turn) * direction + math.sin(turn) * across, dtype=np.float64)


def _perpendiculars(direction: FloatArray) -> tuple[FloatArray, FloatArray]:
    helper = np.array([0.0, 0.0, 1.0]) if abs(direction[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = np.cross(direction, helper)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(direction, e1)


def grow_garden(
    params: GardenStage, setting: Setting, solid: GrowthSolid, rng: np.random.Generator
) -> Garden3:
    """Grow a garden's tubes from the floor of the open space left by `solid`."""
    rng_seeds, rng_grow = rng.spawn(2)
    radius = max(params.radius_mm, DRAWN_RADIUS_MM)
    up = -setting.gravity
    sites = place_sites(setting, solid, params.spacing_mm, rng_seeds)
    floor = sites.normals @ up >= FLOOR_COS
    seeds, normals = sites.points[floor], sites.normals[floor]
    wander = math.radians(params.wander_deg) * math.sqrt(STEP_MM)
    turn = math.radians(BRANCH_TURN_DEG)

    def clearance(q: FloatArray) -> float:
        """Distance from q to the surface of the open space (≤ 0 outside it)."""
        pt = q[None, :]
        if not bool(setting.solid.contains(pt)[0]):
            return 0.0
        d_wall = setting.solid.wall_distance(pt)
        return float(solid.distance(pt, d_wall, setting.height(pt))[0])

    a: list[FloatArray] = []
    b: list[FloatArray] = []
    length: list[float] = []
    cell = 2 * radius  # tubes stop when they reach another seed's tube
    occupied: dict[tuple[int, int, int], int] = {}
    seed_rngs = rng_grow.spawn(len(seeds))
    for own, (seed, normal, srng) in enumerate(zip(seeds, normals, seed_rngs, strict=True)):
        budget = params.volume_mm2 / (2 * params.radius_mm * STEP_MM)  # steps, as in 2D
        start = seed + normal * radius
        # A tip: position, direction, growth so far, and a lower bound on its
        # clearance (distances change by at most a step per step).
        tips: list[tuple[FloatArray, FloatArray, float, float]] = [
            (start, normal, 0.0, clearance(start))
        ]
        for _ in range(MAX_STEPS):
            if not tips or budget <= 0:
                break
            still: list[tuple[FloatArray, FloatArray, float, float]] = []
            for p, direction, grown, clear in tips:
                if budget <= 0:
                    break
                # Buoyancy turns the tube toward vertical; it wanders across it.
                between = math.acos(float(np.clip(direction @ up, -1.0, 1.0)))
                new = _turn_toward(direction, up, params.buoyancy * STEP_MM * between)
                e1, e2 = _perpendiculars(new)
                g = srng.standard_normal(2)
                wandered: FloatArray = new + wander * (float(g[0]) * e1 + float(g[1]) * e2)
                new = wandered / float(np.linalg.norm(wandered))
                q: FloatArray = p + STEP_MM * new
                key = (math.floor(q[0] / cell), math.floor(q[1] / cell), math.floor(q[2] / cell))
                if occupied.get(key, own) != own:
                    continue  # this tip stops at another seed's tube
                clear -= STEP_MM
                if clear < radius:
                    clear = clearance(q)
                    if clear < radius:
                        continue  # or at the wall
                occupied[key] = own
                a.append(p)
                b.append(q)
                length.append(grown)
                budget -= 1
                still.append((q, new, grown + STEP_MM, clear))
                if srng.random() < params.rupture_per_mm * STEP_MM:
                    e1, e2 = _perpendiculars(new)
                    phi = 2 * math.pi * srng.random()
                    side = math.cos(phi) * e1 + math.sin(phi) * e2
                    branch: FloatArray = math.cos(turn) * new + math.sin(turn) * side
                    still.append((q, branch, grown + STEP_MM, clear))
            tips = still
    if not a:
        empty = np.zeros((0, 3))
        return Garden3(a=empty, b=empty, order=np.zeros(0), radius=radius)
    grown_mm = np.array(length)
    return Garden3(
        a=np.array(a),
        b=np.array(b),
        order=grown_mm / max(float(grown_mm.max()), STEP_MM),
        radius=radius,
    )
