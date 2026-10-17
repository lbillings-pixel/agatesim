"""The stages of formation a model goes through, on its deposition-time axis.

Deposition time (`Fields.t_dep`) runs from 0 to 1 over a run. The growth
animation labels that axis with what was forming: wall lining, spherulites,
quartz crystals, settled layers and so on.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from pydantic import BaseModel

from agatesim.models import (
    FrontFeedback,
    Liesegang,
    ProceduralFortification,
    ProceduralGrowth,
    ProceduralWaterline,
    Settling,
    Staged,
)
from agatesim.models.growth import TIME_STEPS, Mode, growth_modes, mode_stages

GROWTH_LABELS = {
    Mode.LINING: "wall lining",
    Mode.SPHERULITIC: "spherulites",
    Mode.CRYSTAL: "quartz crystals",
    Mode.SETTLING: "settled layers",
    Mode.DENDRITE: "branched inclusions",
}


@dataclass(frozen=True)
class Stage:
    start: float  # deposition time, 0..1
    end: float
    label: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def _growth(model: ProceduralGrowth) -> list[Stage]:
    tau = (np.arange(TIME_STEPS) + 0.5) / TIME_STEPS
    mode = growth_modes(model, tau)
    supply = np.clip(model.schedules.silica.sample(tau), 0.0, 1.0)
    out: list[Stage] = []
    for a, b in mode_stages(mode):
        m = Mode(int(mode[a]))
        label = GROWTH_LABELS[m]
        if m is not Mode.DENDRITE and not (supply[a:b] > 0).any():
            label = "no deposition"
        if out and out[-1].label == label:
            out[-1] = Stage(out[-1].start, b / TIME_STEPS, label)
        else:
            out.append(Stage(a / TIME_STEPS, b / TIME_STEPS, label))
    return out


def formation_stages(model: BaseModel) -> list[Stage]:
    match model:
        case ProceduralGrowth():
            return _growth(model)
        case Staged():
            parts = model.order.split("-")
            wall = (
                "precipitation bands (H2)"
                if model.wall_mechanism == "liesegang"
                else "wall lining (H1)"
            )
            names = {
                "wall": wall,
                "floor": "floor layers (H4)",
                "spherulite": "spherulites (H1)",
                "dendrite": "branched inclusions",
            }
            n = len(parts)
            return [Stage(i / n, (i + 1) / n, names[p]) for i, p in enumerate(parts)]
        case FrontFeedback():
            label = "spherulites (H1)" if model.growth_form == "spherulitic" else "wall lining (H1)"
            return [Stage(0.0, 1.0, label)]
        case Settling():
            return [Stage(0.0, 1.0, "floor layers (H4)")]
        case Liesegang():
            return [Stage(0.0, 1.0, "precipitation bands (H2)")]
        case ProceduralFortification():
            return [Stage(0.0, 1.0, "wall lining")]
        case ProceduralWaterline():
            return [Stage(0.0, 1.0, "floor layers")]
        case _:
            return [Stage(0.0, 1.0, "growth")]


def stages_json(model: BaseModel) -> list[dict[str, object]]:
    return [s.to_json() for s in formation_stages(model)]
