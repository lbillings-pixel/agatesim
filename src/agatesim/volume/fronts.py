"""H1 and the staged model in 3D, on exact solids (ADR 0021, ADR 0040).

H1's front history depends only on how far growth has come, so in 3D it is
evaluated at each point from that distance, as in 2D:

- lining: the distance to the nearest solid, the wall or a filament (tube);
- spherulitic: the growth distance from the spherulite that reaches the point
  first (sites on the wall, as in the growth model).

The staged model keeps the solid after each stage exact, as the growth model
does (agatesim.volume.growth): a wall stage that stops early offsets every
piece by its depth, a floor stage adds a bed, a spherulite stage that stops
early adds balls, and a dendrite or garden stage adds its inclusions (ADR 0047).
A later stage's distance to the solid is then the smallest distance to a piece.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from agatesim.fields import Fields, Phase
from agatesim.grid import FloatArray
from agatesim.models import FrontFeedback, Staged
from agatesim.models.front_feedback import (
    FrontHistory,
    band_edges,
    forced_history_from,
    history_fields,
)
from agatesim.models.growth import InclusionGrowth
from agatesim.models.settling import SettledColumn
from agatesim.models.staged import STAGE_SPAN
from agatesim.volume.gardens import grow_garden
from agatesim.volume.growth import (
    Crystals,
    GrowthSolid,
    Inclusion,
    Spherulites,
    grow_aggregate,
    place_sites,
    segment_distance,
    settle_owners,
)
from agatesim.volume.models import Evaluator, Setting, column_of, wall_distance_at
from agatesim.volume.solids import BoolArray


def _tube_mask(setting: Setting, points: FloatArray, inside: BoolArray) -> BoolArray:
    tube = np.zeros(len(points), dtype=bool)
    for t in setting.tubes:
        tube |= inside & (segment_distance(points, t[:3], t[3:6]) <= t[6])
    return tube


def _with_tubes(fields: Fields, tube: BoolArray) -> Fields:
    """Filaments are inclusions; tint 0, the Fe-silicate reported for their cores."""
    if not tube.any():
        return fields
    phase = fields.phase.copy()
    phase[tube] = Phase.INCLUSION
    return replace(
        fields,
        phase=phase,
        band=np.where(tube, -1, fields.band).astype(np.int32),
        impurity=np.where(tube, 0.0, fields.impurity).astype(np.float32),
        translucency=np.where(tube, 0.0, fields.translucency).astype(np.float32),
        t_dep=np.where(tube, np.nan, fields.t_dep).astype(np.float32),
    )


def _spherulites(
    params: FrontFeedback, setting: Setting, solid: GrowthSolid, rng: np.random.Generator
) -> Spherulites:
    sites = place_sites(setting, solid, params.spherulite_spacing_mm, rng)
    metric = Spherulites(sites, params.spherulite_rate_variability)
    settle_owners(metric, setting, solid)
    return metric


def prepare_front_feedback(
    params: FrontFeedback, setting: Setting, rng: np.random.Generator
) -> Evaluator:
    ref = setting.reference
    if params.growth_form == "lining" and not len(setting.tubes):
        # The wall alone: the original 3D H1 (ADR 0021), unchanged.
        history = forced_history_from(params, ref.distance, rng)

        def evaluate_wall(points: FloatArray, inside: BoolArray) -> Fields:
            return history_fields(history, wall_distance_at(setting, points, inside), inside)

        return _with_crystals(params, setting, history, evaluate_wall, rng)

    solid = GrowthSolid(tubes=setting.tubes if len(setting.tubes) else None)
    ref_h = setting.height(ref.points)
    open_ref = solid.distance(ref.points, ref.distance, ref_h) > 0
    metric = (
        _spherulites(params, setting, solid, rng.spawn(1)[0])
        if params.growth_form == "spherulitic"
        else None
    )

    def depth(points: FloatArray, d_wall: FloatArray, h: FloatArray) -> FloatArray:
        if metric is not None:
            return metric.assign(points)[0]
        return np.maximum(solid.distance(points, d_wall, h), 0.0)

    ref_depth = depth(ref.points[open_ref], ref.distance[open_ref], ref_h[open_ref])
    history = forced_history_from(params, ref_depth[np.isfinite(ref_depth)], rng)

    def evaluate(points: FloatArray, inside: BoolArray) -> Fields:
        tube = _tube_mask(setting, points, inside)
        open_ = inside & ~tube
        d = np.full(len(points), np.inf)
        idx = np.flatnonzero(open_)
        d_wall = wall_distance_at(setting, points, inside)
        d[idx] = depth(points[idx], d_wall[idx], setting.height(points[idx]))
        return _with_tubes(history_fields(history, d, open_), tube)

    if params.growth_form == "lining":
        return _with_crystals(params, setting, history, evaluate, rng)
    return evaluate


def _with_crystals(
    params: FrontFeedback,
    setting: Setting,
    history: FrontHistory,
    evaluate: Evaluator,
    rng: np.random.Generator,
) -> Evaluator:
    """H1's quartz filled with crystals, as in 2D (ADR 0037, ADR 0047): they
    nucleate on the chalcedony's inner surface, the lining's solid offset by
    the depth where quartz starts, and compete by geometric selection. H1's
    history says when quartz reaches each point; the crystals say which
    crystal fills it."""
    if not history.quartz.any():
        return evaluate
    start = float(history.depth_mm[int(np.argmax(history.quartz))])
    lining = GrowthSolid(tubes=setting.tubes if len(setting.tubes) else None).dilated(start)
    sites = place_sites(setting, lining, params.quartz_grain_mm, rng.spawn(1)[0])
    crystals = Crystals(sites, params.quartz_elongation, params.quartz_axis_scatter_deg)
    settle_owners(crystals, setting, lining)

    def evaluate_crystals(points: FloatArray, inside: BoolArray) -> Fields:
        fields = evaluate(points, inside)
        quartz = np.flatnonzero(fields.phase == Phase.QUARTZ)
        grain = np.full(len(points), -1, dtype=np.int32)
        grain[quartz] = crystals.assign(points[quartz])[1].astype(np.int32)
        return replace(fields, grain=grain)

    return evaluate_crystals


@dataclass(frozen=True, eq=False)
class _Stage:
    kind: str  # "wall", "spherulite", "floor", "dendrite" or "garden"
    solid: GrowthSolid  # the solid when the stage starts
    limit: float | None  # depth where a first stage stops (None: runs to fill)
    history: FrontHistory | None = None
    t_scale: float = 1.0  # share of the history's time the stage uses
    metric: Spherulites | None = None
    column: SettledColumn | None = None
    aggregate: Inclusion | None = None
    tint: float = 0.0
    band_count: int = 0


def prepare_staged(params: Staged, setting: Setting, rng: np.random.Generator) -> Evaluator:
    """The staged model (agatesim.models.staged) in 3D."""
    order = params.order.split("-")
    rngs = rng.spawn(len(order))
    floor = params.floor.model_copy(update={"gravity_deg": params.gravity_deg})
    ref = setting.reference
    ref_h = setting.height(ref.points)
    total = len(ref.points)
    solid = GrowthSolid(tubes=setting.tubes if len(setting.tubes) else None)
    stages: list[_Stage] = []
    for i, (stage, stage_rng) in enumerate(zip(order, rngs, strict=True)):
        dist = solid.distance(ref.points, ref.distance, ref_h)
        open_ref = dist > 0
        if not open_ref.any():
            break
        first_of_several = i == 0 and i < len(order) - 1
        if stage in ("wall", "spherulite"):
            metric = None
            if stage == "spherulite":
                metric = _spherulites(params.wall, setting, solid, stage_rng.spawn(1)[0])
                depth = metric.assign(ref.points[open_ref])[0]
                depth = depth[np.isfinite(depth)]
            else:
                depth = dist[open_ref]
            history = forced_history_from(params.wall, depth, stage_rng)
            limit, t_scale, reach = None, 1.0, history.stopped_mm
            if first_of_several:
                depths = np.sort(depth)
                limit = float(depths[min(int(params.rim_share * total), len(depths) - 1)])
                at = min(int(np.searchsorted(history.depth_mm, limit)), len(history.time) - 1)
                t_scale = max(float(history.time[at] / history.time[-1]), 1e-9)
                reach = min(reach, limit)
            count = int(np.searchsorted(band_edges(history), reach, side="right")) + 1
            stages.append(_Stage(stage, solid, limit, history, t_scale, metric, band_count=count))
            if limit is not None:
                if metric is None:
                    solid = solid.dilated(limit)
                else:
                    solid = solid.with_balls(metric.s, metric.rate * limit)
        elif stage == "floor":
            column = column_of(floor, setting, ref_h[open_ref], stage_rng)
            count = int(column.layer.max()) + 1 if (column.layer >= 0).any() else 0
            stages.append(_Stage("floor", solid, None, column=column, band_count=count))
            solid = replace(solid, bed=column.top)
        elif stage == "garden":
            garden = grow_garden(params.garden, setting, solid, stage_rng)
            stages.append(_Stage("garden", solid, None, aggregate=garden, tint=params.garden.tint))
            solid = replace(solid, aggregates=(*solid.aggregates, (garden, 0.0)))
        else:
            d = params.dendrite
            how = InclusionGrowth(
                spacing_mm=d.spacing_mm,
                density=d.density,
                amount=d.amount,
                sticking=d.sticking,
                width_mm=d.width_mm,
                gravity_deg=params.gravity_deg,
            )
            aggregate = grow_aggregate(how, setting, solid, stage_rng)
            stages.append(_Stage("dendrite", solid, None, aggregate=aggregate, tint=d.tint))
            solid = replace(solid, aggregates=(*solid.aggregates, (aggregate, 0.0)))

    def evaluate(points: FloatArray, inside: BoolArray) -> Fields:
        n = len(points)
        d_wall = wall_distance_at(setting, points, inside)
        h = setting.height(points)
        tube = _tube_mask(setting, points, inside)
        phase = np.full(n, Phase.HOST, dtype=np.uint8)
        phase[inside] = Phase.VOID
        band = np.full(n, -1, dtype=np.int32)
        impurity = np.zeros(n, dtype=np.float32)
        translucency = np.zeros(n, dtype=np.float32)
        t_dep = np.full(n, np.nan, dtype=np.float32)
        pigment = np.zeros(n, dtype=np.uint8)
        pigmented = False  # whether any stage named its pigments (ADR 0050)
        next_band = 0
        for i, st in enumerate(stages):
            open_now = inside & ~tube & (phase == Phase.VOID)
            if st.kind in ("wall", "spherulite"):
                assert st.history is not None
                if st.metric is not None:
                    dist = np.full(n, np.inf)
                    idx = np.flatnonzero(open_now)
                    dist[idx] = st.metric.assign(points[idx])[0]
                else:
                    dist = np.where(open_now, st.solid.distance(points, d_wall, h), 0.0)
                fields = history_fields(st.history, dist, open_now)
                grown = open_now & (fields.phase != Phase.VOID)
                if st.limit is not None:
                    grown &= dist <= st.limit
            elif st.kind == "floor":
                assert st.column is not None
                fields = st.column.fields(h, open_now)
                grown = open_now & (fields.phase != Phase.VOID)
            else:
                assert st.aggregate is not None
                order_at = np.full(n, np.inf)
                idx = np.flatnonzero(open_now)
                order_at[idx] = st.aggregate.order_at(points[idx])
                grown = open_now & np.isfinite(order_at)
                phase[grown] = Phase.INCLUSION
                impurity[grown] = st.tint
                t_dep[grown] = (i + STAGE_SPAN * order_at[grown]) / len(order)
                continue
            band[grown] = np.where(fields.band[grown] >= 0, fields.band[grown] + next_band, -1)
            next_band += st.band_count
            phase[grown] = fields.phase[grown]
            impurity[grown] = fields.impurity[grown]
            translucency[grown] = fields.translucency[grown]
            if fields.pigment is not None:
                pigment[grown] = fields.pigment[grown]
                pigmented = True
            t = np.nan_to_num(fields.t_dep[grown], nan=1.0) / st.t_scale
            t_dep[grown] = (i + STAGE_SPAN * np.clip(t, 0, 1)) / len(order)
        fields = Fields(
            phase=phase,
            band=band,
            impurity=impurity,
            translucency=translucency,
            t_dep=t_dep,
            grain=np.full(n, -1, dtype=np.int32),
            micro_spacing_um=np.full(n, np.nan, dtype=np.float32),
            pigment=pigment if pigmented else None,
        )
        return _with_tubes(fields, tube)

    return evaluate
