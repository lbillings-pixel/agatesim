"""Chemical-garden tubes: plume agate as a silica garden (ADR 0044).

Plume agate is interpreted as a silica garden ([@goetze2020] §5.5). In a
chemical garden a dissolving seed is wrapped in a semipermeable precipitation
membrane; osmosis swells it until the membrane ruptures, buoyancy carries the
lighter inner solution upward, and the membrane re-precipitates where the
inner and outer solutions meet, so a tube extends upward with some sideways
deviations ([@barge2015]; [@cartwright2026] §4.3). The tube's volume grows at
the rate the inner solution is supplied, so a seed's solution sets how far its
tubes reach ([@barge2015]).

The model grows such tubes, as a 2D slab sees them:

- seeds sit on the floor of the cavity: wall points whose normal points
  upward, where dense seed grains settle, spaced `spacing_mm` apart;
- each tube's tip advances in short steps; buoyancy turns its direction back
  toward vertical (`buoyancy`), and it wanders sideways (`wander_deg`);
- the membrane ruptures now and then (`rupture_per_mm`), and the escaping
  solution starts a side tube (a linking assumption: ruptures as branches);
- each seed's tubes stop when its solution (`volume_mm2`, as an area in the
  slab) is used up, or when they reach the wall or another tube.

Every draw is made in world coordinates per seed, so the tubes don't depend on
the grid's resolution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from agatesim import _scipy
from agatesim.geometry import densify, point_in_polygon
from agatesim.grid import FloatArray, Grid
from agatesim.models.base import Domain
from agatesim.models.growth import wall_sites
from agatesim.params import Nature, param

STEP_MM = 0.05  # length of one growth step
MAX_STEPS = 4000  # per tube
BRANCH_TURN_DEG = 35.0  # a side tube leaves at about this angle
FLOOR_COS = 0.5  # seeds where the wall's inward normal is within 60° of up


class GardenStage(BaseModel):
    """Tubes of a silica garden grown from seeds on the cavity floor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spacing_mm: float = param(
        5.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Mean spacing of the seeds on the cavity floor.",
        explore=(3.5, 7.0),
    )
    volume_mm2: float = param(
        6.0,
        gt=0,
        units="mm²",
        nature=Nature.EFFECTIVE,
        description=(
            "Inner solution per seed, as the area of tube it can build in the slab: sets how "
            "far a seed's tubes reach."
        ),
    )
    radius_mm: float = param(
        0.06,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Tube radius (set in experiments by the flow of the inner solution).",
    )
    buoyancy: float = param(
        1.5,
        ge=0,
        units="1/mm",
        nature=Nature.EFFECTIVE,
        description="How quickly buoyancy turns a tube back toward vertical, per mm of growth.",
        explore=(0.8, 2.5),
    )
    wander_deg: float = param(
        20.0,
        ge=0,
        le=90,
        units="deg",
        nature=Nature.EFFECTIVE,
        description="Sideways wandering of a tube's direction (spread per √mm of growth).",
        explore=(10.0, 30.0),
    )
    rupture_per_mm: float = param(
        0.4,
        ge=0,
        units="1/mm",
        nature=Nature.EFFECTIVE,
        description="Membrane ruptures per mm of tube; each starts a side tube.",
        explore=(0.2, 0.7),
    )
    tint: float = param(
        0.5,
        ge=0,
        le=1,
        units="",
        nature=Nature.PHYSICAL,
        description=(
            "The tube mineral, for its colour: 0 = green Fe-silicate, 0.5 = red-brown Fe "
            "oxide, 1 = black Mn oxide."
        ),
    )


@dataclass(frozen=True)
class Tubes:
    """Tube centrelines as segments, with each segment's growth order in [0, 1]."""

    a: FloatArray  # (n, 2) segment starts, mm
    b: FloatArray  # (n, 2) segment ends, mm
    order: FloatArray  # (n,)
    radius: float


def _seeds(
    domain: Domain, gravity: FloatArray, spacing: float, rng: np.random.Generator
) -> tuple[FloatArray, FloatArray]:
    """Seed points on the cavity floor and their inward normals, blue-noise spaced."""
    sites = wall_sites(domain, spacing, rng)
    up = -gravity
    floor = sites.normals @ up >= FLOOR_COS
    return sites.points[floor], sites.normals[floor]


def grow_tubes(
    params: GardenStage, domain: Domain, gravity: FloatArray, rng: np.random.Generator
) -> Tubes:
    rng_seeds, rng_grow = rng.spawn(2)
    seeds, normals = _seeds(domain, gravity, params.spacing_mm, rng_seeds)
    up = -gravity
    up_angle = math.atan2(float(up[1]), float(up[0]))
    wander = math.radians(params.wander_deg) * math.sqrt(STEP_MM)
    turn = math.radians(BRANCH_TURN_DEG)
    vertices = domain.cavity.vertices
    wall = _scipy.NearestIndex(densify(vertices, domain.cavity.size_mm / 4000))

    def in_open(q: FloatArray) -> bool:
        """Inside the cavity and at least a tube radius from its wall."""
        pt = q[None, :]
        return (
            bool(point_in_polygon(pt, vertices)[0])
            and float(wall.query(pt)[0][0]) >= params.radius_mm
        )

    a: list[FloatArray] = []
    b: list[FloatArray] = []
    length: list[float] = []  # growth so far, for the order
    cell = 2 * params.radius_mm  # tubes stop when they reach another tube
    occupied: dict[tuple[int, int], int] = {}
    seed_rngs = rng_grow.spawn(len(seeds))
    for own, (seed, normal, srng) in enumerate(zip(seeds, normals, seed_rngs, strict=True)):
        budget = params.volume_mm2 / (2 * params.radius_mm * STEP_MM)  # steps of tube
        start = seed + normal * params.radius_mm
        # A seed's tips all grow at once, one step each in turn, sharing its solution.
        tips = [(start, math.atan2(float(normal[1]), float(normal[0])), 0.0)]
        for _ in range(MAX_STEPS):
            if not tips or budget <= 0:
                break
            still: list[tuple[FloatArray, float, float]] = []
            for p, angle, grown in tips:
                if budget <= 0:
                    break
                # Buoyancy turns the tube toward vertical; it wanders sideways.
                delta = (up_angle - angle + math.pi) % (2 * math.pi) - math.pi
                angle += params.buoyancy * STEP_MM * delta + wander * float(srng.standard_normal())
                q = p + STEP_MM * np.array([math.cos(angle), math.sin(angle)])
                key = (math.floor(q[0] / cell), math.floor(q[1] / cell))
                if not in_open(q) or occupied.get(key, own) != own:
                    continue  # this tip stops at the wall or another seed's tube
                occupied[key] = own
                a.append(p)
                b.append(q)
                length.append(grown)
                budget -= 1
                still.append((q, angle, grown + STEP_MM))
                if srng.random() < params.rupture_per_mm * STEP_MM:
                    side = 1.0 if srng.random() < 0.5 else -1.0
                    still.append((q, angle + side * turn, grown + STEP_MM))
            tips = still
    if not a:
        empty = np.zeros((0, 2))
        return Tubes(a=empty, b=empty, order=np.zeros(0), radius=params.radius_mm)
    grown_mm = np.array(length)
    return Tubes(
        a=np.array(a),
        b=np.array(b),
        order=grown_mm / max(float(grown_mm.max()), STEP_MM),
        radius=params.radius_mm,
    )


def rasterise_tubes(tubes: Tubes, grid: Grid) -> NDArray[np.float64]:
    """Earliest growth order in each pixel within a tube (inf elsewhere)."""
    out = np.full(grid.shape, np.inf)
    if not len(tubes.order):
        return out
    xx, yy = grid.coords()
    r = tubes.radius + grid.dx / 2  # keep thin tubes connected at coarse grids
    for a, b, o in zip(tubes.a, tubes.b, tubes.order, strict=True):
        lo = np.minimum(a, b) - r
        hi = np.maximum(a, b) + r
        c0, r1 = np.floor(grid.to_index(np.array([[lo[0], hi[1]]]))[0]).astype(int)
        c1, r0 = np.ceil(grid.to_index(np.array([[hi[0], lo[1]]]))[0]).astype(int)
        c0, c1 = max(c0, 0), min(c1 + 1, grid.nx)
        r1, r0 = max(r1, 0), min(r0 + 1, grid.ny)
        if c0 >= c1 or r1 >= r0:
            continue
        px, py = xx[r1:r0, c0:c1], yy[r1:r0, c0:c1]
        ab = b - a
        t = np.clip(((px - a[0]) * ab[0] + (py - a[1]) * ab[1]) / max(float(ab @ ab), 1e-12), 0, 1)
        d = np.hypot(px - (a[0] + t * ab[0]), py - (a[1] + t * ab[1]))
        sub = out[r1:r0, c0:c1]
        np.minimum(sub, np.where(d <= r, o, np.inf), out=sub)
    return out
