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


@dataclass(frozen=True)
class Fields:
    phase: NDArray[np.uint8]  # Phase values
    band: NDArray[np.int32]  # band index in deposition order; -1 where no band
    impurity: NDArray[np.float32]  # 0..1, iron-oxide stand-in that controls colour
    translucency: NDArray[np.float32]  # 0 (milky, opaque) .. 1 (clear)
    t_dep: NDArray[np.float32]  # normalized deposition time 0..1; NaN where nothing deposited

    def arrays(self) -> dict[str, NDArray[np.generic]]:
        return {
            "phase": self.phase,
            "band": self.band,
            "impurity": self.impurity,
            "translucency": self.translucency,
            "t_dep": self.t_dep,
        }
