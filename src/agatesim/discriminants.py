"""Discriminants: measurements that tell competing formation mechanisms apart.

The criteria ask "does this look like form X?". These ask "which mechanism made
it?". Each is a prediction the mechanistic models of M8 make differently
(ADRs 0013–0017), and each was checked on simulations of known mechanism
(ADR 0018):

- **corner sharpness**: the fortification criterion's turn width over band
  spacing at wall corners. H1 keeps corners (in its boundary-layer
  approximation); Liesegang precipitation (H2) rounds them.
- **ring closure**: the share of bands that are closed rings. H2's rings break
  into rows of spots inward; H1's and procedural bands stay closed.
- **floor-width law**: for horizontal bands, the slope of log layer thickness
  against log cavity width at the layer's height. Settling of pulses of fixed
  volume (H4) spreads each over the width, so the slope is negative (−1 at
  constant dose); layers of imposed thickness give about 0.

The Liesegang spacing law (bands widening inward) was tried and dropped: in
2D, ring breakup hides it (ADR 0018). Like the criteria, these read only Fields
and geometry, so they apply to simulations and to specimen photos alike.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np

from agatesim.criteria.common import band_normals, chalcedony
from agatesim.criteria.fortification import closed_bands, corners_preserved
from agatesim.geometry import Cavity
from agatesim.grid import FloatArray
from agatesim.models.settling import chord_widths
from agatesim.simulate import SimulationResult
from agatesim.specimen.observe import simplify

MIN_POINTS = 6
CORNER_SCALE = 0.01  # outline detail below this share of the cavity's size is not a corner
SLIVER_PX = 3  # bands thinner than this are slivers at band edges, not bands
HORIZONTAL = 0.98  # |band normal · gravity| above this (within ~11°): a horizontal band


@dataclass(frozen=True)
class Fit:
    slope: float | None
    r2: float | None
    points: int

    @classmethod
    def of(cls, x: FloatArray, y: FloatArray) -> Fit:
        ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
        if ok.sum() < MIN_POINTS:
            return cls(None, None, int(ok.sum()))
        lx, ly = np.log(x[ok]), np.log(y[ok])
        if np.ptp(lx) == 0:
            return cls(None, None, int(ok.sum()))
        coef: FloatArray = np.polyfit(lx, ly, 1)
        slope, intercept = float(coef[0]), float(coef[1])
        residual = ly - (slope * lx + intercept)
        r2 = 1 - float(np.sum(residual**2)) / max(float(np.sum((ly - ly.mean()) ** 2)), 1e-12)
        return cls(slope, r2, int(ok.sum()))


@dataclass(frozen=True)
class Discriminants:
    closure: float | None  # share of bands that are closed rings
    corner_ratio: float | None  # turn width / band spacing (sharp < 0.7)
    floor: Fit  # log layer thickness vs log cavity width, horizontal bands only

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def band_shapes(result: SimulationResult) -> dict[str, FloatArray]:
    """Per chalcedony band: area, boundary length, thickness (2 × area ÷ boundary
    length: exact for a ring or a flat layer much wider than it is thick), median
    depth from the wall and median height along −gravity. Rows ordered by band."""
    f = result.fields
    chal = chalcedony(result)
    labels = np.where(chal, f.band, -1)
    ids = np.unique(labels[chal])
    if len(ids) == 0:
        return {k: np.zeros(0) for k in ("band", "area", "length", "thickness", "depth", "height")}
    index = np.full(int(ids.max()) + 2, -1, dtype=np.int64)
    index[ids] = np.arange(len(ids))
    dx = result.grid.dx
    lab = np.where(labels >= 0, index[np.maximum(labels, 0)], -1)
    area = np.bincount(lab[lab >= 0], minlength=len(ids)) * dx * dx
    length = np.zeros(len(ids))
    for a, b in ((lab[:, :-1], lab[:, 1:]), (lab[:-1, :], lab[1:, :])):
        cut = a != b
        for side in (a[cut], b[cut]):
            ok = side >= 0
            length += np.bincount(side[ok], minlength=len(ids)) * dx
    xx, yy = result.grid.coords()
    g = result.gravity
    up = -(xx * g[0] + yy * g[1])
    wall = result.domain.wall_distance
    depth = np.array([float(np.median(wall[lab == i])) for i in range(len(ids))])
    height = np.array([float(np.median(up[lab == i])) for i in range(len(ids))])
    return {
        "band": ids.astype(np.float64),
        "area": area,
        "length": length,
        "thickness": 2 * area / np.maximum(length, 1e-12),
        "depth": depth,
        "height": height,
    }


def _horizontal_bands(result: SimulationResult) -> set[int]:
    band = result.fields.band
    chal = chalcedony(result)
    nx, ny = band_normals(result, sigma_px=1.5)
    g = result.gravity
    keep: set[int] = set()
    edge = chal & ((band != np.roll(band, 1, axis=0)) | (band != np.roll(band, 1, axis=1)))
    ids = np.unique(band[chal]).astype(np.int64)
    for i in range(len(ids)):
        k = int(ids[i])
        on = edge & (band == k)
        if on.sum() < 10:
            continue
        cos: FloatArray = np.abs(nx[on] * g[0] + ny[on] * g[1])
        if float(np.nanmedian(cos)) >= HORIZONTAL:
            keep.add(k)
    return keep


def floor_width_law(result: SimulationResult) -> Fit:
    """Thickness of each horizontal layer against the cavity's width at the layer's
    height, one point per layer."""
    horizontal = _horizontal_bands(result)
    s = band_shapes(result)
    rows = np.array([int(b) in horizontal for b in s["band"]], dtype=bool)
    rows &= s["thickness"] >= SLIVER_PX * result.grid.dx
    if rows.sum() < MIN_POINTS:
        return Fit(None, None, int(rows.sum()))
    vertices = np.asarray(result.domain.cavity.vertices, dtype=np.float64)
    width = chord_widths(vertices, -result.gravity, s["height"][rows])
    return Fit.of(width, s["thickness"][rows])


def at_cavity_scale(result: SimulationResult) -> SimulationResult:
    """The result with its outline simplified at the cavity's own scale, so a traced
    outline's pixel steps don't count as corners. A clean polygon is unchanged."""
    cavity = result.domain.cavity
    vertices = np.asarray(cavity.vertices, dtype=np.float64)
    simple = simplify(vertices, CORNER_SCALE * cavity.size_mm)
    if len(simple) == len(vertices) or len(simple) < 3:
        return result
    outline = Cavity(name=cavity.name, host=cavity.host, vertices=simple)
    return replace(result, domain=replace(result.domain, cavity=outline))


def discriminants(result: SimulationResult) -> Discriminants:
    corner, _ = corners_preserved(at_cavity_scale(result))
    closure, _ = closed_bands(result)
    return Discriminants(
        closure=closure,
        corner_ratio=corner,
        floor=floor_width_law(result),
    )
