"""Fitting a replica: growth-model settings, in the specimen's own outline, whose
band statistics match the photo's (ADR 0011).

A first guess comes straight from the observed statistics:

- lining depth from the open share (how far in the wall-lining reaches);
- band period from the median band thickness (bands are periods of time);
- period variability from the thickness spread (log-normal sigma);
- opacity contrast from the translucency contrast;
- iron supply from the mean stain.

A small seeded search around the guess then reduces the mismatch. This fits
procedural settings to a picture; it says nothing about how the specimen formed
(ADR 0005).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from agatesim.config import RunConfig
from agatesim.models import ProceduralGrowth
from agatesim.schedules import Schedule
from agatesim.simulate import SimulationResult, simulate
from agatesim.stats import BandStats, band_statistics

SEARCH = 10  # candidates tried around the first guess
FIT_RESOLUTION = 256
# Relative weights of the statistics in the mismatch.
WEIGHTS = {
    "thickness_median_mm": 2.0,
    "thickness_cv": 1.0,
    "translucency_contrast": 1.0,
    "iron_mean": 1.0,
    "open_fraction": 2.0,
}


@dataclass(frozen=True)
class Fit:
    config: RunConfig
    stats: BandStats
    target: BandStats
    mismatch: float


def mismatch(a: BandStats, target: BandStats) -> float:
    total = 0.0
    for key, w in WEIGHTS.items():
        x, y = getattr(a, key), getattr(target, key)
        if x is None or y is None:
            continue
        scale = max(abs(float(y)), 0.05)
        total += w * ((float(x) - float(y)) / scale) ** 2
    return math.sqrt(total)


def lining_depth(result: SimulationResult, open_fraction: float) -> float:
    """Wall-lining depth (mm) that leaves `open_fraction` of the cavity open."""
    d = result.domain.wall_distance[result.domain.mask]
    if open_fraction <= 0.002:
        return float(d.max()) * 1.05
    return float(np.quantile(d, 1 - open_fraction))


def first_guess(observed: SimulationResult, target: BandStats) -> ProceduralGrowth:
    depth = max(lining_depth(observed, target.open_fraction), 1.0)
    thickness = target.thickness_median_mm or depth / 20
    cv = target.thickness_cv or 0.35
    contrast = target.translucency_contrast or 0.2
    return ProceduralGrowth(
        gravity_deg=observed.config.model.gravity_deg  # pyright: ignore[reportAttributeAccessIssue]
        if isinstance(observed.config.model, ProceduralGrowth)
        else 270.0,
        growth_mm=depth,
        band_period=float(np.clip(thickness / depth, 0.002, 0.5)),
        period_variability=float(np.clip(math.sqrt(math.log(1 + cv * cv)), 0, 1.5)),
        opacity_contrast=float(np.clip(contrast / 0.35, 0.05, 1.0)),
        iron_variability=0.15,
        iris_fraction=0.0,
        schedules=ProceduralGrowth().schedules.model_copy(
            update={"iron": Schedule(base=float(np.clip(target.iron_mean or 0.2, 0, 1)))}
        ),
    )


def replicate(observed: SimulationResult, seed: int = 0) -> Fit:
    """The best replica found, judged at FIT_RESOLUTION."""
    target = band_statistics(observed)
    base = observed.config.model_copy(
        update={"model": first_guess(observed, target), "archetype": None, "name": "replica"}
    ).with_resolution(FIT_RESOLUTION)
    rng = np.random.default_rng(seed)
    best: Fit | None = None
    for i in range(SEARCH + 1):
        model = base.model
        assert isinstance(model, ProceduralGrowth)
        if i:
            jitter = np.exp(rng.normal(0, 0.25, 3))
            model = model.model_copy(
                update={
                    "band_period": float(np.clip(model.band_period * jitter[0], 0.002, 0.5)),
                    "opacity_contrast": float(np.clip(model.opacity_contrast * jitter[1], 0, 1)),
                    "growth_mm": model.growth_mm * float(jitter[2] ** 0.3),
                }
            )
        config = base.model_copy(update={"model": model, "seed": seed + i})
        stats = band_statistics(simulate(config))
        score = mismatch(stats, target)
        if best is None or score < best.mismatch:
            best = Fit(config=config, stats=stats, target=target, mismatch=score)
    assert best is not None
    return best
