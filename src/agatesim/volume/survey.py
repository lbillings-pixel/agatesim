"""Random cuts through a 3D run: how often a cut shows the form (ADR 0021).

A collector judges an agate from a cut face, at whatever angle the saw went
through. The survey cuts a 3D run at random planes, judges each cut with the
archetype's 2D criteria, and compares the bands' apparent thickness on the cut
with their true thickness, measured in 3D along the wall's normal.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass

import numpy as np

from agatesim.criteria import evaluate
from agatesim.criteria.common import Ray, sample_ray, transition_distances
from agatesim.grid import FloatArray
from agatesim.models import FrontFeedback, ProceduralFortification
from agatesim.simulate import SimulationResult
from agatesim.stats import wall_rays
from agatesim.volume.simulate import VolumeSimulation
from agatesim.volume.slicing import random_cuts

THICKNESS_RAYS = 48
NEAR_WALL_BANDS = 5  # bands counted from the wall, before rays reach the medial region
GRAVITY_BINS = (0.0, 0.5, 0.9, 1.0001)  # |gravity in the cut's plane|, for the summary


@dataclass(frozen=True)
class SurveyCut:
    tilt_deg: float
    azimuth_deg: float
    offset_mm: float
    pieces: int
    gravity_in_plane: float
    passed: bool | None  # None if the cut couldn't be judged
    criteria: dict[str, bool]
    values: dict[str, float | None]
    apparent_thickness_mm: float | None
    error: str | None = None


@dataclass(frozen=True)
class Survey:
    archetype: str | None
    true_thickness_mm: float | None
    cuts: tuple[SurveyCut, ...]

    def summary(self) -> dict[str, object]:
        judged = [c for c in self.cuts if c.passed is not None]
        out: dict[str, object] = {
            "archetype": self.archetype,
            "cuts": len(self.cuts),
            "judged": len(judged),
            "pass_rate": _rate([c.passed for c in judged]),
        }
        ids = sorted({k for c in judged for k in c.criteria})
        out["criteria"] = {k: _rate([c.criteria.get(k) for c in judged]) for k in ids}
        bins: list[dict[str, object]] = []
        for lo, hi in itertools.pairwise(GRAVITY_BINS):
            sel = [c for c in judged if lo <= c.gravity_in_plane < hi]
            bins.append(
                {
                    "gravity_in_plane": [lo, min(hi, 1.0)],
                    "cuts": len(sel),
                    "pass_rate": _rate([c.passed for c in sel]),
                }
            )
        out["by_gravity_in_plane"] = bins
        ratios = [
            c.apparent_thickness_mm / self.true_thickness_mm
            for c in judged
            if c.apparent_thickness_mm is not None and self.true_thickness_mm
        ]
        out["true_thickness_mm"] = self.true_thickness_mm
        if ratios:
            q = np.percentile(ratios, [25, 50, 75])
            out["apparent_over_true"] = {
                "q25": float(q[0]),
                "median": float(q[1]),
                "q75": float(q[2]),
            }
        return out

    def to_json(self) -> dict[str, object]:
        return {"summary": self.summary(), "cuts": [asdict(c) for c in self.cuts]}


def _rate(flags: list[bool | None]) -> float | None:
    known = [f for f in flags if f is not None]
    return sum(known) / len(known) if known else None


def true_thickness(sim: VolumeSimulation, rng: np.random.Generator) -> float | None:
    """Median thickness (mm) of the first bands along the wall's inward normal in 3D, from rays
    started at wall points spread over the cavity, like the 2D statistics. Only
    for models whose bands follow the wall (others return None)."""
    if not isinstance(sim.config.model, ProceduralFortification | FrontFeedback):
        return None
    solid = sim.setting.solid
    ref = sim.setting.reference
    near = np.flatnonzero(ref.distance < 2 * ref.spacing)
    if len(near) == 0:
        return None
    picks = ref.points[rng.choice(near, size=min(THICKNESS_RAYS, len(near)), replace=False)]
    h = 0.02 * ref.spacing
    step = solid.size_mm / 4000
    t = np.arange(0.0, solid.size_mm / 2, step)
    thicknesses: list[float] = []
    for p in picks:
        grad = np.array(
            [
                float(
                    solid.wall_distance((p + h * e)[None])[0]
                    - solid.wall_distance((p - h * e)[None])[0]
                )
                for e in np.eye(3)
            ]
        )
        norm = float(np.linalg.norm(grad))
        if norm < 1e-9:
            continue
        inward = grad / norm
        start = p - float(solid.wall_distance(p[None])[0]) * inward
        pts: FloatArray = start + t[:, None] * inward
        inside = solid.contains(pts)
        band = sim.evaluate(pts, inside).band
        banded = band >= 0
        stop = int(np.argmin(banded[1:])) + 1 if not banded[1:].all() else len(banded)
        thicknesses.extend(_near_wall(Ray(t=t[:stop], band=band[:stop])))
    return float(np.median(thicknesses)) if thicknesses else None


def _near_wall(ray: Ray) -> list[float]:
    """Thicknesses of the first bands crossed by a ray from the wall. Further in,
    rays from different walls meet and cross bands obliquely."""
    edges = transition_distances(ray)
    return np.diff(edges[: NEAR_WALL_BANDS + 1]).tolist()


def apparent_thickness(result: SimulationResult) -> float | None:
    """Median thickness (mm) of the first bands along the cut's own wall normals:
    what a measurement on the cut face finds."""
    thicknesses: list[float] = []
    for origin, normal in wall_rays(result):
        ray = sample_ray(result, origin, normal, result.domain.cavity.size_mm)
        banded = ray.band >= 0
        stop = int(np.argmin(banded[1:])) + 1 if not banded[1:].all() else len(banded)
        thicknesses.extend(_near_wall(Ray(t=ray.t[:stop], band=ray.band[:stop])))
    return float(np.median(thicknesses)) if thicknesses else None


def survey(sim: VolumeSimulation, count: int, resolution: int, seed: int = 0) -> Survey:
    rng_cuts, rng_rays = np.random.default_rng(seed).spawn(2)
    archetype = sim.config.archetype
    thickness = true_thickness(sim, rng_rays)
    cuts: list[SurveyCut] = []
    for spec in random_cuts(sim.setting.solid, count, rng_cuts, resolution):
        tilt, azimuth = round(spec.tilt_deg, 3), round(spec.azimuth_deg, 3)
        offset = round(spec.offset_mm, 4)
        try:
            c = sim.cut(spec)
        except ValueError as exc:
            cuts.append(
                SurveyCut(
                    tilt_deg=tilt,
                    azimuth_deg=azimuth,
                    offset_mm=offset,
                    pieces=0,
                    gravity_in_plane=math.nan,
                    passed=None,
                    criteria={},
                    values={},
                    apparent_thickness_mm=None,
                    error=str(exc),
                )
            )
            continue
        passed: bool | None = None
        criteria: dict[str, bool] = {}
        values: dict[str, float | None] = {}
        if archetype is not None:
            ev = evaluate(archetype, c.result)
            passed = ev.passed
            criteria = {r.id: r.passed for r in ev.results}
            values = {r.id: r.value for r in ev.results}
        cuts.append(
            SurveyCut(
                tilt_deg=tilt,
                azimuth_deg=azimuth,
                offset_mm=offset,
                pieces=c.pieces,
                gravity_in_plane=round(c.gravity_in_plane, 6),
                passed=passed,
                criteria=criteria,
                values=values,
                apparent_thickness_mm=apparent_thickness(c.result) if thickness else None,
            )
        )
    return Survey(archetype=archetype, true_thickness_mm=thickness, cuts=tuple(cuts))
