"""Which pigment colours each band (ADR 0050).

Most colour in chalcedony comes from mineral inclusions: hematite red,
goethite yellow, celadonite green, Mn oxides black; blue comes from light
scattering, white from fine clay inclusions or scattering, and violet from an
amethyst-like iron colour centre ([@powolny2025]; [@zhang2023]). A palette
gives each pigment a weight; each band (or settled pulse) draws one, in
proportion. With only iron weighted, results are as before ADR 0050.
"""

from __future__ import annotations

from typing import cast

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict
from pydantic.config import JsonDict

from agatesim.fields import Pigment
from agatesim.params import Nature, param


def _weight(default: float, what: str) -> float:
    return param(
        default,
        ge=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description=f"Relative share of bands coloured by {what}.",
        explore=(0.0, 1.0),
    )


# Ready-made palettes the app offers (weights not listed are 0).
PALETTE_PRESETS: dict[str, dict[str, float]] = {
    "Iron (as before)": {"iron": 1.0},
    "Red and yellow": {"hematite": 0.6, "goethite": 0.3, "white": 0.1},
    "Blue and white": {"blue": 0.6, "white": 0.4},
    "Green": {"celadonite": 0.6, "white": 0.3, "manganese": 0.1},
    "Black and white": {"manganese": 0.5, "white": 0.5},
    "Violet": {"violet": 0.5, "white": 0.3, "blue": 0.2},
    "Mixed": {"hematite": 0.3, "goethite": 0.2, "white": 0.3, "manganese": 0.1, "violet": 0.1},
}


class Palette(BaseModel):
    """Relative shares of the pigments that colour the bands."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_extra=cast(JsonDict, {"presets": PALETTE_PRESETS})
    )

    iron: float = _weight(1.0, "iron stain without a named mineral (ochre to deep red)")
    hematite: float = _weight(0.0, "hematite (red)")
    goethite: float = _weight(0.0, "goethite (yellow to brown)")
    celadonite: float = _weight(0.0, "celadonite (green)")
    manganese: float = _weight(0.0, "manganese oxide (black)")
    violet: float = _weight(0.0, "an amethyst-like iron colour centre (violet)")
    blue: float = _weight(0.0, "light scattering (blue; no pigment)")
    white: float = _weight(0.0, "fine clay inclusions or scattering (chalky white)")

    def weights(self) -> NDArray[np.float64]:
        """Weights in Pigment order."""
        return np.array(
            [
                self.iron,
                self.hematite,
                self.goethite,
                self.celadonite,
                self.manganese,
                self.violet,
                self.blue,
                self.white,
            ]
        )

    @property
    def iron_only(self) -> bool:
        w = self.weights()
        return bool(w[1:].sum() == 0)

    def draw(self, count: int, rng: np.random.Generator) -> NDArray[np.uint8] | None:
        """A pigment for each of `count` bands, or None for iron throughout.
        Band k's pigment doesn't depend on how many bands there are."""
        if self.iron_only:
            return None
        w = self.weights()
        cumulative = np.cumsum(w / w.sum())
        u = rng.random(count)
        code = np.minimum(np.searchsorted(cumulative, u, side="right"), len(Pigment) - 1)
        return code.astype(np.uint8)
