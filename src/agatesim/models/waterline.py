"""Procedural waterline (Uruguay-type) banding: flat layers filling the cavity floor.

Layers stack upward from the lowest point of the cavity, perpendicular to gravity,
an analogue of gravity settling (hypothesis H4 in docs/science/mechanisms.md).
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from agatesim.fields import Fields
from agatesim.models.base import Domain, fields_from_bands, make_bands, smooth_noise
from agatesim.models.palette import Palette
from agatesim.params import Nature, param


class ProceduralWaterline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["procedural-waterline"] = "procedural-waterline"
    gravity_deg: float = param(
        270.0,
        ge=0,
        lt=360,
        units="deg",
        nature=Nature.PHYSICAL,
        description=(
            "Direction gravity pointed during formation, in the slab plane, "
            "anticlockwise from +x (270 = straight down the page)."
        ),
        key=True,
    )
    fill_height_fraction: float = param(
        0.45,
        gt=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="Height of the layered fill as a fraction of the cavity height.",
        explore=(0.25, 0.7),
    )
    mean_layer_thickness_mm: float = param(
        0.35,
        gt=0,
        units="mm",
        nature=Nature.IMPOSED,
        description="Mean layer thickness.",
        explore=(0.15, 0.8),
        log=True,
    )
    thickness_variability: float = param(
        0.3,
        ge=0,
        le=1.5,
        units="",
        nature=Nature.IMPOSED,
        description="Spread of layer thicknesses (log-normal sigma).",
        explore=(0.1, 0.8),
    )
    alternation: float = param(
        0.6,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="How strictly milky and clear layers alternate.",
        explore=(0.2, 1.0),
    )
    opacity_contrast: float = param(
        0.7,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="Difference in translucency between milky and clear layers.",
        explore=(0.3, 1.0),
    )
    iron: float = param(
        0.15,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="Mean iron staining.",
        explore=(0.0, 0.8),
    )
    iron_variability: float = param(
        0.15,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="Layer-to-layer variation in iron staining.",
        explore=(0.0, 0.5),
    )
    wobble_mm: float = param(
        0.02,
        ge=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Amplitude of irregularity in layer height.",
    )
    wobble_scale_mm: float = param(
        3.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Length scale of layer irregularity.",
    )
    palette: Palette = Field(
        default_factory=Palette,
        description="Which pigments colour the bands, as relative shares (ADR 0050).",
    )

    def gravity(self) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
        th = math.radians(self.gravity_deg)
        return np.array([math.cos(th), math.sin(th)])


def run_waterline(params: ProceduralWaterline, domain: Domain, rng: np.random.Generator) -> Fields:
    rng_bands, rng_noise, rng_palette = rng.spawn(3)
    g = params.gravity()
    xx, yy = domain.grid.coords()
    # Height above the cavity's lowest point, taken from the exact geometry so it
    # doesn't depend on grid resolution.
    vertex_height = -(domain.cavity.vertices @ g)
    height = -(xx * g[0] + yy * g[1]) - float(vertex_height.min())
    level = params.fill_height_fraction * float(np.ptp(vertex_height))
    bands = make_bands(
        total_mm=level,
        mean_thickness_mm=params.mean_layer_thickness_mm,
        variability=params.thickness_variability,
        alternation=params.alternation,
        opacity_contrast=params.opacity_contrast,
        iron=params.iron,
        iron_variability=params.iron_variability,
        rng=rng_bands,
    )
    bands = replace(bands, pigment=params.palette.draw(bands.count, rng_palette))
    coord = height + params.wobble_mm * smooth_noise(domain, params.wobble_scale_mm, rng_noise)
    filled = domain.mask & (coord < level)
    t_dep = np.clip(coord / level, 0, 1)
    return fields_from_bands(domain, coord, filled, bands, t_dep)
