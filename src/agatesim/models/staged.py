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
- **spherulite**: H1 growth radiating from nucleation sites on the wall
  (`growth_form = "spherulitic"`, ADR 0038), stopping when it has filled
  `rim_share` of the cavity. Eye agate is a spherulite stage overgrown by an
  H1 wall stage (ADR 0039).
- **garden**: chemical-garden tubes rising from seeds on the cavity floor,
  driven upward by buoyancy (`agatesim.models.gardens`, ADR 0044). Plume
  agate is a garden stage enclosed by an H1 wall stage.
- **dendrite**: branched inclusions grow from the surface of the open space by
  multi-particle diffusion-limited aggregation (`agatesim.models.dendrites`,
  ADR 0009), the picture of Mn-oxide dendrites growing by attachment of
  diffusing particles [@hou2023]. Later stages grow over every branch. Moss
  agate is a dendrite stage enclosed by an H1 wall stage (ADR 0036).
- **stick**: blade-shaped crystals of an earlier mineral grow from the wall
  with a needle habit, competing by geometric selection like the quartz
  crystals (ADR 0037); later stages line them, and at the end they are
  replaced by quartz or dissolve. Stick agate is a stick stage enclosed by an
  H1 wall stage (ADR 0049).

Each stage reads only the open space the earlier ones left. The order of the
stages is imposed (nature records several), as is the rim's extent. What makes
the bands inside each stage is mechanistic.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from agatesim import _scipy, progress
from agatesim.fields import Fields, Phase
from agatesim.models.base import Domain
from agatesim.models.front_feedback import FrontFeedback, run_front_feedback
from agatesim.models.gardens import GardenStage, grow_tubes, rasterise_tubes
from agatesim.models.growth import InclusionGrowth, StickFill, grow_inclusions, grow_sticks
from agatesim.models.liesegang import Liesegang, run_liesegang
from agatesim.models.settling import Settling, run_settling
from agatesim.params import KEY, Nature, param, used_when

Order = Literal[
    "wall-floor-wall",
    "wall-floor",
    "floor-wall",
    "dendrite-wall",
    "spherulite-wall",
    "garden-wall",
    "stick-wall",
]
WallMechanism = Literal["front-feedback", "liesegang"]
STAGE_SPAN = 0.999  # of a stage's time slot, so stages never share a deposition time


class DendriteStage(BaseModel):
    """Branched inclusions by aggregation of diffusing particles (ADR 0009),
    without the procedural model's upward stand-in for plumes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spacing_mm: float = param(
        4.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Mean spacing of the points on the growth surface where inclusions start.",
    )
    density: float = param(
        0.04,
        gt=0,
        le=0.5,
        units="",
        nature=Nature.EFFECTIVE,
        description=(
            "Concentration of the particles that build inclusions, as a share of the open "
            "space. Higher values give bulkier, less finely branched inclusions."
        ),
        explore=(0.02, 0.08),
    )
    amount: float = param(
        0.08,
        gt=0,
        le=0.6,
        units="",
        nature=Nature.EFFECTIVE,
        description="Total inclusion material, as a share of the open space it grows into.",
        explore=(0.04, 0.15),
    )
    sticking: float = param(
        0.5,
        gt=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description=(
            "Chance that a particle sticks when it touches an inclusion. Lower values "
            "give denser, more compact branches."
        ),
        explore=(0.3, 0.8),
    )
    width_mm: float = param(
        0.12,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Width of the finest branches (the lattice cell the particles walk on).",
    )
    cells_3d: float = param(
        4.0,
        ge=0.5,
        le=64,
        units="million cells",
        nature=Nature.EFFECTIVE,
        description=(
            "In 3D, the most cells the inclusions' lattice may have, in millions; beyond "
            "it the lattice coarsens and the finest branches widen. About 40 keeps "
            "0.12 mm branches in a 40 mm cavity, in about 20 s with or without a GPU (ADR 0061)."
        ),
    )
    tint: float = param(
        1.0,
        ge=0,
        le=1,
        units="",
        nature=Nature.PHYSICAL,
        description=(
            "The inclusion mineral, for its colour: 0 = green Fe-silicate (celadonite-like), "
            "0.5 = red-brown Fe oxide, 1 = black Mn oxide."
        ),
    )


class StickStage(BaseModel):
    """Blade-shaped crystals grown from the wall before the agate (ADR 0049)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spacing_mm: float = param(
        6.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Mean spacing of the points on the wall where stick crystals nucleate.",
        explore=(3.5, 6.5),
    )
    length_mm: float = param(
        7.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description=(
            "How far the crystals' tips grow before the silica arrives (the timing of a "
            "change in conditions)."
        ),
        explore=(3.5, 7.0),
    )
    elongation: float = param(
        20.0,
        ge=2,
        le=60,
        units="",
        nature=Nature.EFFECTIVE,
        description=(
            "How much faster the crystals grow along their long axis than across it (their "
            "habit): a stick is about half this many times longer than wide."
        ),
        explore=(10.0, 20.0),
    )
    axis_scatter_deg: float = param(
        25.0,
        ge=0,
        le=90,
        units="deg",
        nature=Nature.EFFECTIVE,
        description="Spread of crystal axes about the wall normal where they nucleate.",
        explore=(10.0, 40.0),
    )
    fill: StickFill = Field(
        default="quartz",
        json_schema_extra=KEY,
        description=(
            "What replaces the crystals at the end: quartz (a pseudomorph) or nothing (they "
            "dissolve and leave hollow moulds)."
        ),
    )


class Staged(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["mechanistic-staged"] = "mechanistic-staged"
    order: Order = Field(
        default="wall-floor-wall",
        description="The stages, in deposition order.",
        json_schema_extra=KEY,
    )
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
            "Share of the cavity the first wall-lining or spherulite stage fills before conditions "
            "change (the timing of that change, not a property of any band)."
        ),
        explore=(0.15, 0.45),
    )
    wall_mechanism: WallMechanism = Field(
        default="front-feedback",
        description="What makes the wall-lining bands: front feedback (H1) or Liesegang (H2).",
        json_schema_extra={**used_when({"order": ["wall"]}), **KEY},
    )
    wall: FrontFeedback = Field(
        default_factory=FrontFeedback,
        description="The H1 wall and spherulite stages (with the front-feedback wall mechanism).",
        json_schema_extra=used_when(
            {"order": ["spherulite"]}, {"order": ["wall"], "wall_mechanism": ["front-feedback"]}
        ),
    )
    liesegang: Liesegang = Field(
        default_factory=Liesegang,
        description="The H2 wall stages (with the Liesegang wall mechanism).",
        json_schema_extra=used_when({"order": ["wall"], "wall_mechanism": ["liesegang"]}),
    )
    floor: Settling = Field(
        default_factory=Settling,
        description="The H4 floor stage (orders with a floor).",
        json_schema_extra=used_when({"order": ["floor"]}),
    )
    garden: GardenStage = Field(
        default_factory=GardenStage,
        description="The chemical-garden stage: tubes rising from the floor (garden-wall order).",
        json_schema_extra=used_when({"order": ["garden"]}),
    )
    dendrite: DendriteStage = Field(
        default_factory=DendriteStage,
        description="The dendrite stage: branched inclusions (the dendrite-wall order).",
        json_schema_extra=used_when({"order": ["dendrite"]}),
    )
    stick: StickStage = Field(
        default_factory=StickStage,
        description="The stick stage: blade crystals lined by later bands (stick-wall order).",
        json_schema_extra=used_when({"order": ["stick"]}),
    )

    def gravity(self) -> NDArray[np.float64]:
        return self.floor.model_copy(update={"gravity_deg": self.gravity_deg}).gravity()


def _sub_domain(domain: Domain, region: NDArray[np.bool_]) -> Domain:
    """The open region as a domain of its own: distances are to the nearest solid
    (the wall or earlier deposits). The whole cavity keeps its exact wall distance."""
    if np.array_equal(region, domain.mask):
        return domain
    distance = _scipy.distance_to_false(region, domain.grid.dx)
    return Domain(cavity=domain.cavity, grid=domain.grid, mask=region, wall_distance=distance)


def _dendrite_fields(
    params: Staged,
    domain: Domain,
    open_space: NDArray[np.bool_],
    first: bool,
    rng: np.random.Generator,
) -> Fields:
    """Inclusions grown into the open space; their deposition time is the order
    in which they attached."""
    d = params.dendrite
    how = InclusionGrowth(
        spacing_mm=d.spacing_mm,
        density=d.density,
        amount=d.amount,
        sticking=d.sticking,
        width_mm=d.width_mm,
        gravity_deg=params.gravity_deg,
    )
    order = grow_inclusions(how, domain, open_space, first, rng)
    grown = open_space & np.isfinite(order)
    shape = domain.grid.shape
    phase = np.full(shape, Phase.VOID, dtype=np.uint8)
    phase[grown] = Phase.INCLUSION
    return Fields(
        phase=phase,
        band=np.full(shape, -1, dtype=np.int32),
        impurity=np.where(grown, d.tint, 0.0).astype(np.float32),
        translucency=np.zeros(shape, dtype=np.float32),
        t_dep=np.where(grown, order, np.nan).astype(np.float32),
        grain=np.full(shape, -1, dtype=np.int32),
        micro_spacing_um=np.full(shape, np.nan, dtype=np.float32),
    )


def _garden_fields(
    params: Staged, domain: Domain, open_space: NDArray[np.bool_], rng: np.random.Generator
) -> Fields:
    """Chemical-garden tubes grown into the open space; their deposition time is
    the order in which they grew."""
    tubes = grow_tubes(params.garden, domain, params.gravity(), rng)
    order = np.where(open_space, rasterise_tubes(tubes, domain.grid), np.inf)
    grown = open_space & np.isfinite(order)
    shape = domain.grid.shape
    phase = np.full(shape, Phase.VOID, dtype=np.uint8)
    phase[grown] = Phase.INCLUSION
    return Fields(
        phase=phase,
        band=np.full(shape, -1, dtype=np.int32),
        impurity=np.where(grown, params.garden.tint, 0.0).astype(np.float32),
        translucency=np.zeros(shape, dtype=np.float32),
        t_dep=np.where(grown, order, np.nan).astype(np.float32),
        grain=np.full(shape, -1, dtype=np.int32),
        micro_spacing_um=np.full(shape, np.nan, dtype=np.float32),
    )


def _stick_fields(
    params: Staged,
    domain: Domain,
    open_space: NDArray[np.bool_],
    first: bool,
    rng: np.random.Generator,
) -> Fields:
    """Stick crystals grown into the open space; their deposition time is how
    far the tips had grown. They stand as quartz until run_staged replaces them."""
    s = params.stick
    order, owner = grow_sticks(
        domain,
        open_space,
        first,
        rng,
        spacing_mm=s.spacing_mm,
        length_mm=s.length_mm,
        elongation=s.elongation,
        scatter_deg=s.axis_scatter_deg,
    )
    grown = open_space & np.isfinite(order)
    shape = domain.grid.shape
    phase = np.full(shape, Phase.VOID, dtype=np.uint8)
    phase[grown] = Phase.QUARTZ
    return Fields(
        phase=phase,
        band=np.full(shape, -1, dtype=np.int32),
        impurity=np.zeros(shape, dtype=np.float32),
        translucency=np.where(grown, 0.9, 0.0).astype(np.float32),
        t_dep=np.where(grown, order, np.nan).astype(np.float32),
        grain=np.where(grown, owner, -1).astype(np.int32),
        micro_spacing_um=np.full(shape, np.nan, dtype=np.float32),
    )


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
    grain = np.full(shape, -1, dtype=np.int32)
    pigment = np.zeros(shape, dtype=np.uint8)
    pigmented = False  # whether any stage named its pigments (ADR 0050)
    stick = np.zeros(shape, dtype=bool)
    cavity_pixels = int(domain.mask.sum())
    next_band = 0
    next_grain = 0
    parts = progress.shares([1.0] * len(stages))  # a stage's share of the progress bar
    for i, (stage, stage_rng) in enumerate(zip(stages, rngs, strict=True)):
        lo, hi = parts[i]
        open_space = domain.mask & (phase == Phase.VOID)
        if not open_space.any():
            break
        if stage == "wall":
            sub = _sub_domain(domain, open_space)
            if params.wall_mechanism == "liesegang":
                region = None if np.array_equal(open_space, domain.mask) else open_space
                with progress.span(lo, hi):
                    fields = run_liesegang(params.liesegang, domain, stage_rng, region=region)
            else:
                with progress.span(lo, hi):
                    fields = run_front_feedback(params.wall, sub, stage_rng, first=sub is domain)
            grown = open_space & (fields.phase != Phase.VOID)
            if i == 0 and i < len(stages) - 1:
                # The first wall stage stops when it has filled the rim's share.
                depths = np.sort(sub.wall_distance[open_space])
                limit = depths[min(int(params.rim_share * cavity_pixels), len(depths) - 1)]
                grown &= sub.wall_distance <= limit
        elif stage == "spherulite":
            sub = _sub_domain(domain, open_space)
            eyes = params.wall.model_copy(
                update={"growth_form": "spherulitic", "supply_ends_at": params.rim_share}
            )
            with progress.span(lo, hi):
                fields = run_front_feedback(eyes, sub, stage_rng, first=sub is domain)
            grown = open_space & (fields.phase != Phase.VOID)
        elif stage == "garden":
            fields = _garden_fields(params, domain, open_space, stage_rng)
            grown = open_space & (fields.phase != Phase.VOID)
        elif stage == "dendrite":
            fields = _dendrite_fields(params, domain, open_space, i == 0, stage_rng)
            grown = open_space & (fields.phase != Phase.VOID)
        elif stage == "stick":
            fields = _stick_fields(params, domain, open_space, i == 0, stage_rng)
            grown = open_space & (fields.phase != Phase.VOID)
            stick |= grown
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
        if fields.pigment is not None:
            pigment[grown] = fields.pigment[grown]
            pigmented = True
        crystal = grown & (fields.grain >= 0)
        if crystal.any():
            grain[crystal] = fields.grain[crystal] + next_grain
            next_grain = int(grain.max()) + 1
        # Deposition order: stage i takes the times [i, i + 1) / stages.
        t = np.nan_to_num(fields.t_dep[grown], nan=1.0)
        if stage == "wall" and i == 0 and i < len(stages) - 1:
            t = t / max(float(t.max()), 1e-9)
        t_dep[grown] = (i + STAGE_SPAN * np.clip(t, 0, 1)) / len(stages)
    if params.stick.fill == "hollow" and stick.any():
        # The crystals dissolve after the agate, leaving moulds (ADR 0049).
        phase[stick] = Phase.VOID
        translucency[stick] = 0.0
        t_dep[stick] = np.nan
        grain[stick] = -1
    return Fields(
        phase=phase,
        band=band,
        impurity=impurity,
        translucency=translucency,
        t_dep=t_dep,
        grain=grain,
        micro_spacing_um=np.full(shape, np.nan, dtype=np.float32),
        pigment=pigment if pigmented else None,
    )
