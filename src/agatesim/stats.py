"""Band statistics: a compact, comparable summary of a result.

Like the criteria, these read only Fields and geometry, so the same numbers can
describe a simulation run or, later, a specimen photo (ADR 0006).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from agatesim.criteria.common import Ray, sample_ray, transition_distances
from agatesim.fields import Phase
from agatesim.simulate import SimulationResult

RAYS = 48


@dataclass(frozen=True)
class BandStats:
    band_count: int
    thickness_mean_mm: float | None
    thickness_median_mm: float | None
    thickness_cv: float | None  # coefficient of variation of band thickness
    translucency_contrast: float | None  # std of band translucency
    iron_mean: float | None
    chalcedony_fraction: float
    quartz_fraction: float
    open_fraction: float
    crystal_count: int

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def _wall_rays(result: SimulationResult) -> list[tuple[np.ndarray, np.ndarray]]:
    """Points spread evenly along the wall, each with its inward normal."""
    v = result.domain.cavity.vertices
    end = np.roll(v, -1, axis=0)
    lengths = np.linalg.norm(end - v, axis=1)
    perimeter = float(lengths.sum())
    rays: list[tuple[np.ndarray, np.ndarray]] = []
    cumulative = np.concatenate([[0.0], np.cumsum(lengths)])
    for j in range(RAYS):
        s = (j + 0.5) * perimeter / RAYS
        i = int(np.searchsorted(cumulative, s, side="right")) - 1
        t = (s - cumulative[i]) / lengths[i]
        edge = (end[i] - v[i]) / lengths[i]
        rays.append((v[i] + t * (end[i] - v[i]), np.array([-edge[1], edge[0]])))
    return rays


def band_statistics(result: SimulationResult) -> BandStats:
    f = result.fields
    mask = result.domain.mask
    area = max(int(mask.sum()), 1)
    chal = f.phase == Phase.CHALCEDONY
    present = np.unique(f.band[chal])

    thicknesses: list[float] = []
    for origin, normal in _wall_rays(result):
        ray = sample_ray(result, origin, normal, result.domain.cavity.size_mm)
        # Only count the uninterrupted banded run from the wall inward.
        inside = ray.band >= 0
        stop = int(np.argmin(inside[1:])) + 1 if not inside[1:].all() else len(inside)
        edges = transition_distances(Ray(t=ray.t[:stop], band=ray.band[:stop]))
        thicknesses.extend(np.diff(edges).tolist())

    per_band = [float(f.translucency[chal & (f.band == k)].mean()) for k in present.tolist()]
    th = np.array(thicknesses)
    has = len(th) > 0
    return BandStats(
        band_count=len(present),
        thickness_mean_mm=float(th.mean()) if has else None,
        thickness_median_mm=float(np.median(th)) if has else None,
        thickness_cv=float(th.std() / th.mean()) if has and th.mean() > 0 else None,
        translucency_contrast=float(np.std(per_band)) if per_band else None,
        iron_mean=float(f.impurity[chal].mean()) if chal.any() else None,
        chalcedony_fraction=float(chal.sum()) / area,
        quartz_fraction=float((f.phase == Phase.QUARTZ).sum()) / area,
        open_fraction=float((f.phase == Phase.VOID).sum()) / area,
        crystal_count=len(np.unique(f.grain[f.grain >= 0])),
    )
