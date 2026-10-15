"""Criteria for combined fortification and waterline banding.

Each band is classified from the fields alone:

- **horizontal**: its boundary is a straight line perpendicular to gravity;
- **wall-parallel**: its boundary is clearly curved and not perpendicular to
  gravity overall. This includes bands that drape over an earlier flat floor
  and then rise along the walls;
- **other**: anything ambiguous (short, or both curved and roughly level).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from agatesim.criteria.common import band_normals, line_fit_rms, pixel_points, upper_boundaries
from agatesim.criteria.types import Measurement
from agatesim.simulate import SimulationResult

MIN_PIXELS = 20
FLAT_RMS = 0.005  # fraction of cavity size
CURVED_RMS = 0.01
LEVEL_COS = 0.95
NOT_LEVEL_COS = 0.9


@dataclass(frozen=True)
class BandClass:
    band: int
    kind: str  # "horizontal" | "wall" | "other"


def classify_bands(result: SimulationResult) -> list[BandClass]:
    band = result.fields.band
    boundary = upper_boundaries(result)
    nx, ny = band_normals(result)
    g = result.gravity
    size = result.domain.cavity.size_mm
    out: list[BandClass] = []
    ids: list[int] = np.unique(band[boundary]).astype(np.int64).tolist()
    for k in ids:
        on = boundary & (band == k)
        if on.sum() < MIN_PIXELS:
            continue
        rms = line_fit_rms(pixel_points(result.grid, on)) / size
        cos = np.abs(nx[on] * g[0] + ny[on] * g[1])
        level = float(cos.mean())
        if rms < FLAT_RMS and level > LEVEL_COS:
            kind = "horizontal"
        elif rms > CURVED_RMS and level < NOT_LEVEL_COS:
            kind = "wall"
        else:
            kind = "other"
        out.append(BandClass(band=int(k), kind=kind))
    return out


def two_domains(result: SimulationResult) -> Measurement:
    classes = classify_bands(result)
    h = sum(c.kind == "horizontal" for c in classes)
    w = sum(c.kind == "wall" for c in classes)
    return float(min(h, w)), f"{h} horizontal and {w} wall-parallel bands"


def staged(result: SimulationResult) -> Measurement:
    """Number of uninterrupted runs of one domain, in deposition order."""
    kinds = [c.kind for c in classify_bands(result) if c.kind != "other"]
    if not kinds:
        return None, "no classifiable bands"
    runs = 1 + sum(a != b for a, b in pairwise(kinds))
    order = " → ".join(k for i, k in enumerate(kinds) if i == 0 or kinds[i - 1] != k)
    return float(runs), f"sequence: {order}"


def evaluate(result: SimulationResult) -> dict[str, Measurement]:
    return {"two-domains": two_domains(result), "staged": staged(result)}
