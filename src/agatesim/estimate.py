"""Rough cost of an action before it runs: time and peak memory (ADR 0060).

The app shows a caution badge beside an action whose estimate passes
HEAVY_SECONDS or HEAVY_GB. Estimates come from what was measured to drive cost,
on the owner's machine (RTX 4070, 2026-10-18), and aim at the right size, not
precision: the number of pixels or voxels, H2's and the dendrites' lattices
(and whether a GPU runs them), H1's stiffness at high rejection or trapping
velocity, and the cuts of a survey. Each estimate names its main reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from agatesim import _rd
from agatesim.config import RunConfig
from agatesim.geometry import signed_area
from agatesim.models import FrontFeedback, Liesegang, ProceduralGrowth, Settling, Staged
from agatesim.models.dendrites import MAX_CELLS as DLA_2D_MAX_CELLS
from agatesim.models.liesegang import MAX_CELLS as H2_2D_MAX_CELLS
from agatesim.volume.config import VolumeConfig
from agatesim.volume.dendrites import MAX_CELLS as DENDRITE_DEFAULT_CELLS
from agatesim.volume.liesegang import MAX_CELLS as H2_MAX_CELLS

HEAVY_SECONDS = 30.0
HEAVY_GB = 2.0
BASE_GB = 0.4  # the app itself, with its libraries loaded

# Calibration (see ADR 0060 for the runs behind each number).
PIXEL_SECONDS = 1.0e-6  # simulating and rendering, per output pixel
JUDGE_SECONDS = 2.0e-6  # judging a result against its form's tests, per pixel
PIXEL_BYTES = 150.0  # peak bytes per pixel of a full run (fields, judging, writing)
# H1's growth history switches sharply from about a second to about fifty (its
# rhythm turns stiff) above a trapping velocity that falls as rejection rises.
# Measured on a grid of rejection 1.25-5 by trapping velocity 0.78-3.12; the
# boundary is drawn a little on the cautious side of the measured switch.
H1_FAST_SECONDS = 1.0
H1_STIFF_SECONDS = 55.0
H1_BOUNDARY_REJECTION = (1.25, 1.4, 1.55, 1.7, 1.85, 2.0)
H1_BOUNDARY_TRAPPING = (1.55, 1.3, 1.05, 0.85, 0.85, 0.0)  # stiff at or above
H1_DELTA = 0.0016  # the boundary layer the table was measured at (mm)
H1_DELTA_POWER = 0.9  # time grows as (H1_DELTA / delta) ** power (13.8 s at 5e-5 mm)
H2_2D_GPU_SECONDS = 15.0  # liesegang-nodule (2D) on the GPU
H2_2D_CELLS = 600_000  # its lattice
H2_3D_GPU_SECONDS = 97.0  # liesegang-nodule-3d on the GPU
H2_3D_CELLS = 38_000_000
H2_CPU_FACTOR = 70.0  # the CPU against the GPU, for H2
H2_WORK_POWER = 5 / 3  # time grows as cells ** power: cells times steps across
H2_3D_BYTES = 66.0  # peak bytes per lattice cell
DLA_CPU_SECONDS = 126.0  # moss-fine-3d's aggregation on the CPU
DLA_GPU_SECONDS = 15.0  # and on the GPU
DLA_CELLS = 30_000_000
DLA_BYTES = 12.0  # peak bytes per lattice cell
DLA_GPU_PARTICLES = 100_000  # the dendrite engine's GPU threshold (agatesim._dla)
DLA_UPWARD_FACTOR = 2.3  # plumes' upward bias: particles take longer to stick
DLA_2D_SECONDS = 34.0  # 2D dendrites on their full lattice (moss at 0.005 mm branches)
DLA_2D_POWER = 1.2  # time grows as cells ** power (moss at 0.12 mm: about 1.5 s)
H4_SECONDS = 4.6  # H4's settling at 12 pulses 2.5 settling times apart (any resolution)
VOXEL_SECONDS = 0.35e-6  # evaluating a 3D model, per voxel or cut pixel
VOXEL_BYTES = 50.0  # a full 3D run's peak bytes per voxel
CUT_SECONDS = 0.5  # judging one surveyed cut at 512 px
# Forms whose cuts take longer: stick's tests (a distance map per stick); moss,
# plume and botryoidal cuts search dendrites or spheres (moss as its finest preset)
CUT_FACTOR = {"stick": 3.7, "moss": 2.8, "botryoidal": 2.0, "plume": 1.8}


@dataclass(frozen=True)
class Estimate:
    seconds: float
    memory_gb: float
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def heavy(self) -> bool:
        return self.seconds > HEAVY_SECONDS or self.memory_gb > HEAVY_GB

    def plus(self, other: Estimate) -> Estimate:
        """One action after another: times add, memory is the larger peak."""
        return Estimate(
            self.seconds + other.seconds,
            max(self.memory_gb, other.memory_gb),
            self.reasons + other.reasons,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "seconds": round(self.seconds, 1),
            "memory_gb": round(self.memory_gb, 2),
            "heavy": self.heavy,
            "reasons": list(self.reasons),
        }


def _gpu() -> bool:
    return _rd.gpu_in_use()


def _where(gpu: bool) -> str:
    return "on the GPU" if gpu else "on the CPU (no GPU found)"


def h1_seconds(params: FrontFeedback) -> float:
    """H1's growth history: stiff above a trapping velocity that falls as
    rejection rises (always at rejection 2 and above), and longer with a thinner
    boundary layer (more bands)."""
    limit = float(np.interp(params.rejection, H1_BOUNDARY_REJECTION, H1_BOUNDARY_TRAPPING))
    stiff = params.trapping_velocity >= limit
    base = H1_STIFF_SECONDS if stiff else H1_FAST_SECONDS
    return base * (H1_DELTA / params.boundary_layer_mm) ** H1_DELTA_POWER


def _h1(params: FrontFeedback) -> Estimate:
    s = h1_seconds(params)
    reasons = ("H1's rhythm is stiff at these settings",) if s > HEAVY_SECONDS / 2 else ()
    return Estimate(s, BASE_GB, reasons)


def _dendrites_2d(width_mm: float, bounds_mm2: float) -> Estimate:
    cells = min(bounds_mm2 / width_mm**2, DLA_2D_MAX_CELLS)
    s = DLA_2D_SECONDS * (cells / DLA_2D_MAX_CELLS) ** DLA_2D_POWER
    reasons = (
        (f"dendrite lattice of {cells / 1e6:.1f} million cells",) if s > HEAVY_SECONDS / 2 else ()
    )
    return Estimate(s, BASE_GB, reasons)


def _dendrites_on(model: ProceduralGrowth) -> bool:
    d = model.schedules.dendrite
    return d.base > 0 or any(e.value > 0 for e in d.events)


def _h4(params: Settling) -> Estimate:
    s = H4_SECONDS * (params.pulses / 12) * (params.pulse_interval / 2.5)
    reasons = (f"{params.pulses} settling pulses",) if s > HEAVY_SECONDS / 2 else ()
    return Estimate(s, BASE_GB, reasons)


def _h2_2d(params: Liesegang, area_mm2: float) -> Estimate:
    cells = min(area_mm2 / params.lattice_mm**2, H2_2D_MAX_CELLS)
    gpu = _gpu()
    s = H2_2D_GPU_SECONDS * (cells / H2_2D_CELLS) ** H2_WORK_POWER
    if not gpu:
        s *= H2_CPU_FACTOR
    reason = f"H2 lattice of {cells / 1e6:.1f} million cells, {_where(gpu)}"
    return Estimate(s, BASE_GB + 60 * cells / 1e9, (reason,))


def _model_2d(model: object, area_mm2: float, bounds_mm2: float) -> Estimate:
    match model:
        case ProceduralGrowth() if _dendrites_on(model):
            return _dendrites_2d(model.dendrite_width_mm, bounds_mm2)
        case FrontFeedback():
            return _h1(model)
        case Liesegang():
            return _h2_2d(model, area_mm2)
        case Settling():
            return _h4(model)
        case Staged():
            order = model.order.split("-")
            walls = order.count("wall") + order.count("spherulite")
            if model.wall_mechanism == "liesegang":
                wall = _h2_2d(model.liesegang, area_mm2)
            else:
                e = _h1(model.wall)
                wall = Estimate(e.seconds * walls, e.memory_gb, e.reasons)
            if "floor" in order:
                wall = wall.plus(_h4(model.floor))
            if "dendrite" in order:
                wall = wall.plus(_dendrites_2d(model.dendrite.width_mm, bounds_mm2))
            return wall
        case _:
            return Estimate(0.0, BASE_GB)


def run_2d(config: RunConfig, resolution: int) -> Estimate:
    """A 2D simulation at `resolution` px across: the preview or a full run."""
    cavity = config.cavity.build()
    area = abs(signed_area(cavity.vertices))
    xmin, ymin, xmax, ymax = cavity.bounds()
    bounds = (xmax - xmin) * (ymax - ymin)
    pixels = resolution * resolution
    pixel = Estimate(
        pixels * (PIXEL_SECONDS + JUDGE_SECONDS),
        BASE_GB + PIXEL_BYTES * pixels / 1e9,
        (f"{resolution} px",)
        if pixels * (PIXEL_SECONDS + JUDGE_SECONDS) > HEAVY_SECONDS / 2
        else (),
    )
    return _model_2d(config.model, area, bounds).plus(pixel)


def _lattice_cells(config: VolumeConfig, h: float, budget: int) -> int:
    lo, hi = config.solid.build().bounds()
    cells = float(np.prod(hi - lo)) / h**3
    return int(min(cells, budget))


def _dendrites(
    config: VolumeConfig,
    width_mm: float,
    density: float,
    budget_millions: float,
    upward: float = 0.0,
) -> Estimate:
    cells = _lattice_cells(config, width_mm, round(budget_millions * 1e6))
    gpu = _gpu() and density * cells * 0.5 >= DLA_GPU_PARTICLES  # about half the lattice is open
    scale = (cells / DLA_CELLS) ** H2_WORK_POWER
    s = (DLA_GPU_SECONDS if gpu else DLA_CPU_SECONDS) * scale
    if upward > 0:
        s *= DLA_UPWARD_FACTOR
    reason = f"dendrite lattice of {cells / 1e6:.0f} million cells, {_where(gpu)}"
    big = cells > DENDRITE_DEFAULT_CELLS
    return Estimate(s, BASE_GB + DLA_BYTES * cells / 1e9, (reason,) if big or s > 10 else ())


def build_3d(config: VolumeConfig) -> Estimate:
    """Preparing a 3D formation (the 3D view and its cut need it first)."""
    model = config.model
    match model:
        case Liesegang():
            cells = _lattice_cells(config, model.lattice_mm, H2_MAX_CELLS)
            gpu = _gpu()
            s = H2_3D_GPU_SECONDS * (cells / H2_3D_CELLS) ** H2_WORK_POWER
            if not gpu:
                s *= H2_CPU_FACTOR
            reason = f"H2 lattice of {cells / 1e6:.0f} million cells, {_where(gpu)}"
            return Estimate(s, BASE_GB + H2_3D_BYTES * cells / 1e9, (reason,))
        case FrontFeedback():
            return _h1(model)
        case Staged():
            order = model.order.split("-")
            out = _h1(model.wall)
            if "floor" in order:
                out = out.plus(_h4(model.floor))
            if "dendrite" in order:
                d = model.dendrite
                out = out.plus(_dendrites(config, d.width_mm, d.density, d.cells_3d))
            return out
        case ProceduralGrowth() if _dendrites_on(model):
            return _dendrites(
                config,
                model.dendrite_width_mm,
                model.dendrite_density,
                model.dendrite_cells_3d,
                model.dendrite_upward,
            )
        case Settling():
            return _h4(model)
        case _:
            return Estimate(0.0, BASE_GB)


def view_3d(config: VolumeConfig, view_resolution: int, cut_resolution: int) -> Estimate:
    """Building the 3D view and its cut: the formation, then the voxels and cut."""
    points = view_resolution**3 + cut_resolution**2
    return build_3d(config).plus(Estimate(points * VOXEL_SECONDS, BASE_GB))


def _cuts(cuts: int, cut_resolution: int, archetype: str | None) -> Estimate:
    s = cuts * CUT_SECONDS * CUT_FACTOR.get(archetype or "", 1.0) * (cut_resolution / 512) ** 2
    reason = (f"{cuts} cuts at {cut_resolution} px",) if s > HEAVY_SECONDS / 2 else ()
    return Estimate(s, BASE_GB, reason)


def survey_3d_prepared(config: VolumeConfig, cuts: int, cut_resolution: int) -> Estimate:
    """Surveying random cuts of a formation already prepared."""
    return _cuts(cuts, cut_resolution, config.archetype)


def survey_3d(config: VolumeConfig, cuts: int, cut_resolution: int) -> Estimate:
    """Surveying random cuts (the formation first, if it isn't prepared yet)."""
    return build_3d(config).plus(_cuts(cuts, cut_resolution, config.archetype))


def run_3d(
    config: VolumeConfig, resolution: int, survey_cuts: int, cut_resolution: int
) -> Estimate:
    """A full 3D run: the formation, its voxels, the configured cut and a survey."""
    voxels = resolution**3
    fields = Estimate(
        voxels * VOXEL_SECONDS,
        BASE_GB + VOXEL_BYTES * voxels / 1e9,
        (f"{resolution}³ voxels",) if voxels * VOXEL_SECONDS > HEAVY_SECONDS / 2 else (),
    )
    out = build_3d(config).plus(fields)
    return out.plus(_cuts(survey_cuts, cut_resolution, config.archetype)) if survey_cuts else out
