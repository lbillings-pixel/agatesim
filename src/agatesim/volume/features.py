"""World-fixed features of a stone's wall (ADR 0077): where bands thin to nothing.

Bands are the level sets of one arrival depth: wall distance plus a wobble. So
they keep their thickness all around the wall, and they cannot end. Agate's wall
bands do end at infiltration channels, by thinning smoothly to zero toward a
vanishing line [@walger2009, pp. 116, 118]. Each channel here is such a line on
the inner face of the clear outer layer, and it delays the arrival depth near
that line. The bands are still contours of one function, so they never cross,
and what a band is made of still depends on growth time alone.

Everything here follows from the seed and the cavity, and is evaluated at any
point, so every resolution and every cut sees the same channels. A channel's
draws come from its own stream, which leaves the model's other streams alone.

Every number and coupling is `effective`: the sources describe the form, not a
rate, and nothing rendered from this is evidence for how channels form.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import numpy as np

from agatesim.grid import FloatArray
from agatesim.models.growth import ProceduralGrowth
from agatesim.volume.models import Setting
from agatesim.volume.solids import Solid

FEATURE_STREAM = 0x0F3A  # spawn key, far above any count of spawned streams
FADE_DEPTHS = 3.0  # a channel's effect ends at this many of its depths from the surface
LINE_PIECES = 4  # straight pieces of a vanishing line, which follows the curved wall
SURFACE_MIN_MM = 0.05  # with no clear layer the line sits this close to the wall
GRADIENT_STEP_MM = 0.02
PLACEMENT_TRIES = 64
WALK_ROUNDS = 3
STRAIGHT_WALL = 0.9  # the wall distance's slope must reach this where a line is placed


def feature_stream(rng: np.random.Generator) -> np.random.Generator:
    """The stream of a run's features: a function of the run's seed that leaves
    `rng` untouched, so the streams it spawns stay as they were."""
    seq = cast(np.random.SeedSequence, rng.bit_generator.seed_seq)
    key = (*seq.spawn_key, FEATURE_STREAM)
    return np.random.default_rng(np.random.SeedSequence(seq.entropy, spawn_key=key))


def _length(v: FloatArray) -> float:
    return math.sqrt(float(v @ v))


def _segment_distance_sq(p: FloatArray, a: FloatArray, b: FloatArray) -> FloatArray:
    ab = b - a
    denominator = float(ab @ ab)
    u = np.clip((p - a) @ ab / denominator, 0, 1) if denominator > 0 else np.zeros(len(p))
    off = p - (a + u[:, None] * ab)
    return np.sum(off * off, axis=1)


def _fade(x: FloatArray) -> FloatArray:
    """Falls smoothly from 1 at x = 0 to 0 at x = 1; its steepest slope is 1.5."""
    u = np.clip(x, 0.0, 1.0)
    return 1.0 - u * u * (3.0 - 2.0 * u)


@dataclass(frozen=True, eq=False)
class WallChannel:
    """A vanishing line on the surface at `surface_mm` from the wall, and how far
    around it the bands are disturbed: `lateral_mm` along the wall on each side
    and `depth_mm`, the thickness of the stack of bands that thin to zero."""

    line: FloatArray  # (LINE_PIECES + 1, 3) points on the surface
    lateral_mm: float
    depth_mm: float
    surface_mm: float

    @property
    def fade_mm(self) -> float:
        return FADE_DEPTHS * self.depth_mm

    def lateral(self, points: FloatArray, d_wall: FloatArray, slack_mm: float = 0.0) -> FloatArray:
        """Distance along the wall from the line, as a share of `lateral_mm`,
        capped at 1 (no effect). `slack_mm` widens the search for callers whose
        depth differs from d_wall by up to that much."""
        s = np.ones(len(points))
        centre: FloatArray = self.line[len(self.line) // 2]
        half = float(np.sqrt(np.sum((self.line - centre) ** 2, axis=1)).max())
        reach = half + math.hypot(self.lateral_mm, self.fade_mm + slack_mm)
        off = points - centre
        near = np.flatnonzero(np.sum(off * off, axis=1) < reach * reach)
        if not len(near):
            return s
        p = points[near]
        to_line = np.full(len(near), np.inf)
        for i in range(len(self.line) - 1):
            to_line = np.minimum(to_line, _segment_distance_sq(p, self.line[i], self.line[i + 1]))
        z = np.maximum(d_wall[near] - self.surface_mm, 0.0)
        along = np.sqrt(np.maximum(to_line - z * z, 0.0))
        s[near] = np.minimum(along / self.lateral_mm, 1.0)
        return s

    def influence(self, points: FloatArray, d_wall: FloatArray) -> FloatArray:
        """How strongly the channel acts at each point, 0 to 1: 1 on the line and
        0 outside a compact zone. Depends on place alone, not on any band."""
        z = d_wall - self.surface_mm
        s = self.lateral(points, d_wall)
        out = (1 - s * s) ** 2 * _fade(np.maximum(z, 0.0) / self.fade_mm)
        return np.where(z >= 0, out, 0.0)

    def delay(self, level: FloatArray, s: FloatArray) -> FloatArray:
        """How much later (mm of arrival depth) the front reaches each point, given
        its arrival depth `level` and its share `s` from `lateral`.

        On the wall side, a band at depth D lies at z = D s² u / (1 - D u / H) to
        first order: a parabola with the wall as its tangent at the line, so all
        bands in the stack share a tangent there [@walger2009, p. 116] and thin
        to zero. Their thickness relative to normal is s² / (s² + u). Going inward
        the delay's slope stays above -1/2 (FADE_DEPTHS), so arrival depth keeps
        rising and bands cannot fold; bands beyond the stack pass over the line.
        """
        h = self.depth_mm
        z = np.maximum(level - self.surface_mm, 0.0)
        wide = (1 - s * s) ** 2 * _fade(z / self.fade_mm)
        safe = np.maximum(z + h * s * s, 1e-12)
        return h * wide * z / safe


@dataclass(frozen=True, eq=False)
class FeatureLayer:
    """The features of one stone. With none, every delay is zero."""

    channels: tuple[WallChannel, ...] = ()

    def influence(self, points: FloatArray, d_wall: FloatArray) -> FloatArray:
        """Per channel, (n, channels): how strongly each acts at each point, 0 to 1.
        This is what along-band materials will read too (ADR 0077 section 5)."""
        out = np.zeros((len(points), len(self.channels)))
        for i, channel in enumerate(self.channels):
            out[:, i] = channel.influence(points, d_wall)
        return out

    def delay(self, points: FloatArray, wall_level: FloatArray, d_wall: FloatArray) -> FloatArray:
        """How much later (mm of arrival depth) the front reaches each point, from
        its wall distance and the wall front's own arrival depth. A channel belongs
        to the wall, so a front from a filament is delayed only as much as the wall's
        at that place. Each channel's result rises with the wall front's depth, and
        so does their largest, so overlapping channels cannot fold."""
        out = np.zeros(len(wall_level))
        if not self.channels or not len(wall_level):
            return out
        slack = float(np.abs(wall_level - d_wall).max())
        for channel in self.channels:
            s = channel.lateral(points, d_wall, slack)
            out = np.maximum(out, channel.delay(wall_level, s))
        return out


def _gradient(solid: Solid, p: FloatArray) -> FloatArray:
    grad = np.zeros_like(p)
    for axis in range(3):
        e = np.zeros(3)
        e[axis] = GRADIENT_STEP_MM
        grad[:, axis] = (solid.wall_distance(p + e) - solid.wall_distance(p - e)) / (
            2 * GRADIENT_STEP_MM
        )
    return grad


def _on_surface(solid: Solid, p: FloatArray, surface_mm: float) -> tuple[FloatArray, FloatArray]:
    """Points moved onto the surface at `surface_mm`, and the wall distance's slope
    there (it strays from 1 at a kink, where the point cannot be placed)."""
    q = p
    for _ in range(4):
        grad = _gradient(solid, q)
        size2 = np.maximum(np.sum(grad * grad, axis=1, keepdims=True), 1e-12)
        q = q - (solid.wall_distance(q) - surface_mm)[:, None] * grad / size2
    grad = _gradient(solid, q)
    return q, np.sqrt(np.sum(grad * grad, axis=1))


def _walk(
    solid: Solid, start: FloatArray, along: FloatArray, step: float, surface_mm: float, pieces: int
) -> FloatArray | None:
    """Points `step` apart along the surface from `start`, or None if the walk leaves
    the wall's smooth part. Each step aims a little inward, since a tangent step
    leaves a cavity whose wall curves toward it."""
    out = np.zeros((pieces, 3))
    q, direction = start, along
    for i in range(pieces):
        normal: FloatArray = _gradient(solid, q[None, :])[0]
        size = _length(normal)
        if size < STRAIGHT_WALL:
            return None
        reach = step
        move = direction
        for _ in range(WALK_ROUNDS):  # projection stretches a step, by the wall's curvature
            aim = q + reach * direction + 0.5 * step * normal / size
            if not solid.contains(aim[None, :])[0]:
                return None
            placed, slope = _on_surface(solid, aim[None, :], surface_mm)
            if slope[0] < STRAIGHT_WALL or abs(solid.wall_distance(placed)[0] - surface_mm) > 0.01:
                return None
            move = placed[0] - q
            reach *= step / max(_length(move), 1e-12)
        direction = move / max(_length(move), 1e-12)
        out[i] = q = q + move
    return out


def _place_channel(
    params: ProceduralGrowth, setting: Setting, surface_mm: float, rng: np.random.Generator
) -> WallChannel:
    """A vanishing line drawn from the reference lattice, which depends only on the
    cavity, and walked along the surface away from kinks in the wall distance."""
    solid = setting.solid
    ref = setting.reference
    anchors = ref.points[ref.distance < surface_mm + 2 * ref.spacing]
    step = params.channel_length_mm / LINE_PIECES
    for _ in range(PLACEMENT_TRIES):
        anchor = anchors[int(rng.integers(len(anchors)))]
        turn = 2 * math.pi * float(rng.random())
        placed, slope = _on_surface(solid, anchor[None, :], surface_mm)
        centre: FloatArray = placed[0]
        if slope[0] < STRAIGHT_WALL or abs(solid.wall_distance(placed)[0] - surface_mm) > 0.01:
            continue
        grad: FloatArray = _gradient(solid, placed)[0]
        normal = grad / _length(grad)
        # Two directions in the wall's plane, then the line's direction between them.
        helper: FloatArray = np.eye(3)[int(np.argmin(np.abs(normal)))]
        u = cast(FloatArray, np.cross(normal, helper))
        u = u / _length(u)
        v = cast(FloatArray, np.cross(normal, u))
        along = math.cos(turn) * u + math.sin(turn) * v
        pieces = LINE_PIECES // 2
        ahead = _walk(solid, centre, along, step, surface_mm, pieces)
        behind = _walk(solid, centre, -along, step, surface_mm, pieces)
        if ahead is not None and behind is not None:
            line = np.vstack([behind[::-1], centre, ahead])
            return WallChannel(line, params.channel_lateral_mm, params.channel_depth_mm, surface_mm)
    raise ValueError("no place on this cavity's wall can hold a channel of this length")


def wall_features(
    params: ProceduralGrowth, setting: Setting, rng: np.random.Generator
) -> FeatureLayer:
    """The stone's features, from the run's generator (which stays untouched), so
    a caller can find them again: `wall_features(model, setting, default_rng(seed))`.
    Each channel has its own stream, so adding one leaves the others in place."""
    if params.channel_count == 0:
        return FeatureLayer()
    surface_mm = max(params.clear_layer_mm, SURFACE_MIN_MM)
    streams = feature_stream(rng).spawn(params.channel_count)
    return FeatureLayer(tuple(_place_channel(params, setting, surface_mm, r) for r in streams))
