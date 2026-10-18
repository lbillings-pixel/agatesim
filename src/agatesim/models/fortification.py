"""Procedural fortification banding: bands at fixed depths from the cavity wall.

Because band position is a function of distance to the wall, bands keep the wall's
convex corners as sharp angular turns, as fortification agate does. This imposes
the form rather than explaining it (ADR 0003).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from agatesim import _scipy
from agatesim.fields import Fields
from agatesim.models.base import Domain, fields_from_bands, make_bands, smooth_noise
from agatesim.models.palette import Palette
from agatesim.params import Nature, param


class ProceduralFortification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["procedural-fortification"] = "procedural-fortification"
    mean_band_thickness_mm: float = param(
        0.5, gt=0, units="mm", nature=Nature.IMPOSED, description="Mean band thickness."
    )
    thickness_variability: float = param(
        0.35,
        ge=0,
        le=1.5,
        units="",
        nature=Nature.IMPOSED,
        description="Spread of band thicknesses (log-normal sigma).",
    )
    fill_fraction: float = param(
        1.0,
        gt=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="How far banding reaches toward the centre (1 = completely filled).",
    )
    alternation: float = param(
        0.7,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="How strictly milky and clear bands alternate (0 = random, 1 = strict).",
    )
    opacity_contrast: float = param(
        0.8,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="Difference in translucency between milky and clear bands.",
    )
    iron: float = param(
        0.25, ge=0, le=1, units="", nature=Nature.IMPOSED, description="Mean iron staining."
    )
    iron_variability: float = param(
        0.25,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="Band-to-band variation in iron staining.",
    )
    wobble_mm: float = param(
        0.15,
        ge=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Amplitude of irregularity in band position.",
    )
    wobble_scale_mm: float = param(
        2.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Length scale of band irregularity.",
    )
    corner_rounding_mm: float = param(
        0.0,
        ge=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Smooths band corners (0 = bands keep the wall's sharp corners).",
    )
    palette: Palette = Field(
        default_factory=Palette,
        description="Which pigments colour the bands, as relative shares (ADR 0050).",
    )


def run_fortification(
    params: ProceduralFortification, domain: Domain, rng: np.random.Generator
) -> Fields:
    rng_bands, rng_noise, rng_palette = rng.spawn(3)
    d = domain.wall_distance
    depth = params.fill_fraction * float(d.max())
    bands = make_bands(
        total_mm=depth,
        mean_thickness_mm=params.mean_band_thickness_mm,
        variability=params.thickness_variability,
        alternation=params.alternation,
        opacity_contrast=params.opacity_contrast,
        iron=params.iron,
        iron_variability=params.iron_variability,
        rng=rng_bands,
    )
    bands = replace(bands, pigment=params.palette.draw(bands.count, rng_palette))
    coord = d
    if params.corner_rounding_mm > 0:
        coord = _scipy.gaussian(coord, sigma=params.corner_rounding_mm / domain.grid.dx)
    noise = smooth_noise(domain, params.wobble_scale_mm, rng_noise)
    # Taper the wobble to zero at the wall so the outermost band hugs it.
    taper = np.clip(d / (2 * params.wobble_mm), 0, 1) if params.wobble_mm > 0 else 0.0
    coord = coord + params.wobble_mm * noise * taper
    filled = domain.mask & (coord < depth)
    t_dep = np.clip(coord / depth, 0, 1)
    return fields_from_bands(domain, coord, filled, bands, t_dep)
