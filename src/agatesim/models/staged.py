"""Mechanistic combined form: wall-lining (H1 or H2) and settled floor (H4) stages.

Agates that show both forms record a change in conditions during filling: a
wall-parallel rim, then horizontal layers settled on the floor, then often more
wall-parallel bands draping over them ([@goetze2020] §4.1.2). Lu and Sunagawa
propose that one silica solution does both: small particles join the fibrous
wall bands, while particles that grew past a critical size stay in suspension
and settle out as horizontal layers [@lu1994].

This model chains the two verified mechanisms in the order given:

- **wall**: front feedback (H1, `agatesim.models.front_feedback`) grows bands
  inward from every solid surface: the cavity wall and whatever earlier stages
  left. The first wall stage stops when it has filled `rim_share` of the
  cavity, and the last runs until the space is full or its silica runs out.
  With `wall_mechanism = "liesegang"`, Liesegang precipitation (H2,
  `agatesim.models.liesegang`) fills the wall stages instead; in a later stage
  its reactant enters through every surface of the open space, earlier
  deposits included (an assumption).
- **floor**: hindered settling (H4, `agatesim.models.settling`) packs pulses of
  particles up from the lowest point of the open space left so far.

Each stage reads only the open space the earlier ones left. The order of the
stages is imposed (nature records several), as is the rim's extent. What makes
the bands inside each stage is mechanistic.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from agatesim import _scipy
from agatesim.fields import Fields, Phase
from agatesim.models.base import Domain
from agatesim.models.front_feedback import FrontFeedback, run_front_feedback
from agatesim.models.liesegang import Liesegang, run_liesegang
from agatesim.models.settling import Settling, run_settling
from agatesim.params import Nature, param

Order = Literal["wall-floor-wall", "wall-floor", "floor-wall"]
WallMechanism = Literal["front-feedback", "liesegang"]
STAGE_SPAN = 0.999  # of a stage's time slot, so stages never share a deposition time


class Staged(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["mechanistic-staged"] = "mechanistic-staged"
    order: Order = Field(default="wall-floor-wall", description="The stages, in deposition order.")
    gravity_deg: float = param(
        270.0,
        ge=0,
        lt=360,
        units="deg",
        nature=Nature.PHYSICAL,
        description="Direction of gravity in the slab (270 = down).",
    )
    rim_share: float = param(
        0.3,
        gt=0,
        lt=1,
        units="× cavity",
        nature=Nature.EFFECTIVE,
        description=(
            "Share of the cavity the first wall-lining stage fills before conditions "
            "change (the timing of that change, not a property of any band)."
        ),
    )
    wall_mechanism: WallMechanism = Field(
        default="front-feedback",
        description="What makes the wall-lining bands: front feedback (H1) or Liesegang (H2).",
    )
    wall: FrontFeedback = Field(default_factory=FrontFeedback, description="The H1 wall stages.")
    liesegang: Liesegang = Field(
        default_factory=Liesegang, description="The H2 wall stages (wall_mechanism = liesegang)."
    )
    floor: Settling = Field(default_factory=Settling, description="The H4 floor stage.")

    def gravity(self) -> NDArray[np.float64]:
        return self.floor.model_copy(update={"gravity_deg": self.gravity_deg}).gravity()


def _sub_domain(domain: Domain, region: NDArray[np.bool_]) -> Domain:
    """The open region as a domain of its own: distances are to the nearest solid
    (the wall or earlier deposits). The whole cavity keeps its exact wall distance."""
    if np.array_equal(region, domain.mask):
        return domain
    distance = _scipy.distance_to_false(region, domain.grid.dx)
    return Domain(cavity=domain.cavity, grid=domain.grid, mask=region, wall_distance=distance)


def run_staged(params: Staged, domain: Domain, rng: np.random.Generator) -> Fields:
    stages = params.order.split("-")
    rngs = rng.spawn(len(stages))
    floor = params.floor.model_copy(update={"gravity_deg": params.gravity_deg})
    shape = domain.grid.shape
    phase = np.full(shape, Phase.HOST, dtype=np.uint8)
    phase[domain.mask] = Phase.VOID
    band = np.full(shape, -1, dtype=np.int32)
    impurity = np.zeros(shape, dtype=np.float32)
    translucency = np.zeros(shape, dtype=np.float32)
    t_dep = np.full(shape, np.nan, dtype=np.float32)
    cavity_pixels = int(domain.mask.sum())
    next_band = 0
    for i, (stage, stage_rng) in enumerate(zip(stages, rngs, strict=True)):
        open_space = domain.mask & (phase == Phase.VOID)
        if not open_space.any():
            break
        if stage == "wall":
            sub = _sub_domain(domain, open_space)
            if params.wall_mechanism == "liesegang":
                region = None if np.array_equal(open_space, domain.mask) else open_space
                fields = run_liesegang(params.liesegang, domain, stage_rng, region=region)
            else:
                fields = run_front_feedback(params.wall, sub, stage_rng)
            grown = open_space & (fields.phase != Phase.VOID)
            if i == 0 and i < len(stages) - 1:
                # The first wall stage stops when it has filled the rim's share.
                depths = np.sort(sub.wall_distance[open_space])
                limit = depths[min(int(params.rim_share * cavity_pixels), len(depths) - 1)]
                grown &= sub.wall_distance <= limit
        else:
            fields = run_settling(floor, domain, stage_rng, region=open_space)
            grown = open_space & (fields.phase != Phase.VOID)
        if not grown.any():
            continue
        stage_band = np.where(grown & (fields.band >= 0), fields.band, -1)
        ids = np.unique(stage_band[stage_band >= 0])
        relabel = np.full(int(stage_band.max()) + 1 if len(ids) else 1, -1, dtype=np.int32)
        relabel[ids] = next_band + np.arange(len(ids), dtype=np.int32)
        band[grown] = np.where(
            stage_band[grown] >= 0, relabel[np.maximum(stage_band[grown], 0)], -1
        )
        next_band += len(ids)
        phase[grown] = fields.phase[grown]
        impurity[grown] = fields.impurity[grown]
        translucency[grown] = fields.translucency[grown]
        # Deposition order: stage i takes the times [i, i + 1) / stages.
        t = np.nan_to_num(fields.t_dep[grown], nan=1.0)
        if stage == "wall" and i == 0 and i < len(stages) - 1:
            t = t / max(float(t.max()), 1e-9)
        t_dep[grown] = (i + STAGE_SPAN * np.clip(t, 0, 1)) / len(stages)
    return Fields(
        phase=phase,
        band=band,
        impurity=impurity,
        translucency=translucency,
        t_dep=t_dep,
        grain=np.full(shape, -1, dtype=np.int32),
        micro_spacing_um=np.full(shape, np.nan, dtype=np.float32),
    )
