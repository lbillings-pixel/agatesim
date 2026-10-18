"""Material fields: the common output of every formation model (ADR 0003).

Archetype criteria, the renderer and the UI read only these fields, so
procedural and mechanistic models are interchangeable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np
from numpy.typing import NDArray


class Phase(IntEnum):
    HOST = 0
    CHALCEDONY = 1
    VOID = 2
    QUARTZ = 3
    INCLUSION = 4  # foreign solid inside the cavity: tube filaments (later, dendrites)


class Pigment(IntEnum):
    """What colours a pixel of chalcedony (ADR 0050). Most colour in chalcedony
    comes from mineral inclusions; blue and white from how it scatters light."""

    IRON = 0  # iron stain without a named mineral: ochre to deep red as it increases
    HEMATITE = 1  # red
    GOETHITE = 2  # yellow to brown
    CELADONITE = 3  # green Fe-silicate
    MANGANESE = 4  # black Mn oxide
    VIOLET = 5  # an amethyst-like iron colour centre
    BLUE = 6  # light scattering, no pigment
    WHITE = 7  # fine clay inclusions or scattering: chalky white


@dataclass(frozen=True)
class Fields:
    phase: NDArray[np.uint8]  # Phase values
    band: NDArray[np.int32]  # band index in deposition order; -1 where no band
    # 0..1, iron-oxide stand-in that controls colour. For inclusions it is the
    # mineral tint: 0 green Fe-silicate, 0.5 red-brown Fe oxide, 1 black Mn oxide.
    impurity: NDArray[np.float32]
    translucency: NDArray[np.float32]  # 0 (milky, opaque) .. 1 (clear)
    t_dep: NDArray[np.float32]  # normalized deposition time 0..1; NaN where nothing deposited
    grain: NDArray[np.int32]  # crystal id for macrocrystalline quartz; -1 elsewhere
    # Spacing (µm) of regular micro-banding within the visible bands, which acts
    # as a diffraction grating (iris agate); NaN where the micro-banding is irregular.
    micro_spacing_um: NDArray[np.float32]
    # Pigment values: what `impurity` measures the strength of in chalcedony.
    # None means iron throughout (the colour every model had before ADR 0050).
    pigment: NDArray[np.uint8] | None = None

    def arrays(self) -> dict[str, NDArray[np.generic]]:
        out: dict[str, NDArray[np.generic]] = {
            "micro_spacing_um": self.micro_spacing_um,
            "phase": self.phase,
            "band": self.band,
            "impurity": self.impurity,
            "translucency": self.translucency,
            "t_dep": self.t_dep,
            "grain": self.grain,
        }
        if self.pigment is not None:
            out["pigment"] = self.pigment
        return out
