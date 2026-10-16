"""Corner sharpness on images (ADR 0026): synthetic corners of known radius."""

from __future__ import annotations

import math

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from agatesim.specimen.corner_fit import (
    band_widths_along,
    face_thinning,
    measure_corner,
    measure_marked_boundary,
    measure_mitre,
)


def _nested_corner(
    radius: float, angle_deg: float = 100.0, size: int = 400, gap: int = 40
) -> np.ndarray:
    """Alternating light and dark bands nested in a corner of the given interior
    angle, each band boundary rounded with the given radius, lightly blurred."""
    img = Image.new("RGB", (size, size), (40, 40, 50))
    draw = ImageDraw.Draw(img)
    half = math.radians(angle_deg) / 2
    apex = np.array([size * 0.2, size * 0.8])
    bis = np.array([1.0, -1.0]) / math.sqrt(2)
    u1 = np.array(
        [math.cos(math.atan2(bis[1], bis[0]) + half), math.sin(math.atan2(bis[1], bis[0]) + half)]
    )
    u2 = np.array(
        [math.cos(math.atan2(bis[1], bis[0]) - half), math.sin(math.atan2(bis[1], bis[0]) - half)]
    )
    for k in range(7):  # outermost first, so each inner band is drawn on top
        offset = k * gap
        v = apex + bis * (offset / math.sin(half))
        r = radius
        centre = v + bis * (r / math.sin(half))
        tangent = r / math.tan(half)
        a = v + u1 * tangent
        b = v + u2 * tangent
        pts = [tuple(v + u1 * 2 * size), tuple(a)]
        if r > 0:
            start = math.atan2(a[1] - centre[1], a[0] - centre[0])
            end = math.atan2(b[1] - centre[1], b[0] - centre[0])
            sweep = (end - start + math.pi) % (2 * math.pi) - math.pi
            for s in np.linspace(0, 1, 40):
                ang = start + s * sweep
                pts.append((centre[0] + r * math.cos(ang), centre[1] + r * math.sin(ang)))
        pts += [tuple(b), tuple(v + u2 * 2 * size)]
        colour = (220, 210, 190) if k % 2 == 0 else (120, 90, 60)
        draw.polygon([(float(x), float(y)) for x, y in pts], fill=colour)
    return np.asarray(img.filter(ImageFilter.GaussianBlur(1.0)))


@pytest.mark.parametrize("radius", [0.0, 12.0, 25.0])
def test_fillet_radius_is_recovered(radius: float) -> None:
    m = measure_corner(_nested_corner(radius), max_radius=60.0)
    assert len(m.boundaries) >= 3
    radii = [b.radius_px for b in m.boundaries]
    assert abs(float(np.median(radii)) - radius) <= max(4.0, 0.2 * radius)
    assert m.spacing_px is not None
    assert m.spacing_px == pytest.approx(40, rel=0.25)


def test_sharp_corners_score_below_rounded_ones() -> None:
    sharp = measure_corner(_nested_corner(0.0), max_radius=60.0).ratios()
    round_ = measure_corner(_nested_corner(25.0), max_radius=60.0).ratios()
    assert np.median(sharp) < 0.15 < np.median(round_)


def _mitre(size: int = 400) -> tuple[tuple[float, float], tuple[float, float]]:
    """The synthetic corner's bisector, from near the apex inward."""
    apex = np.array([size * 0.2, size * 0.8])
    bis = np.array([1.0, -1.0]) / math.sqrt(2)
    a, b = apex + 30 * bis, apex + 250 * bis
    return (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))


def test_mitre_width_grows_with_rounding() -> None:
    """Across the mitre, sharp corners turn within the measuring scale; rounded
    ones over about 2 rho sin(turn / 4) more."""
    start, end = _mitre()
    widths = {}
    for radius in (0.0, 25.0, 50.0):
        m = measure_mitre(_nested_corner(radius, gap=60), start, end, half_width_px=60)
        assert m.turn_deg == pytest.approx(80, abs=8)
        assert m.spacing_px == pytest.approx(60, rel=0.3)
        widths[radius] = m.width_px
    expected = 2 * 50 * math.sin(math.radians(80) / 4)  # about 34 px at rho = 50
    assert widths[0.0] < 15
    assert widths[0.0] < widths[25.0] < widths[50.0]
    assert widths[50.0] - widths[0.0] == pytest.approx(expected, rel=0.4)


@pytest.mark.parametrize("radius", [0.0, 30.0])
def test_a_marked_boundary_is_fitted(radius: float) -> None:
    """A corner marked by hand: the boundary through the mark is fitted, and the
    neighbouring boundary gives the band spacing."""
    img = _nested_corner(radius, gap=60)
    apex = np.array([400 * 0.2, 400 * 0.8]) + 60 * 2 / math.sqrt(2) * np.array(
        [1.0, -1.0]
    ) / math.sqrt(2) * math.sqrt(2)
    b, spacing = measure_marked_boundary(
        img, (float(apex[0]), float(apex[1])), search_px=150, max_radius=80, min_points=40
    )
    assert b is not None
    assert b.radius_px == pytest.approx(radius, abs=max(5.0, 0.25 * radius))
    assert spacing == pytest.approx(60, rel=0.3)


def _marker_band(taper: float, size: int = 900, width: float = 60.0) -> np.ndarray:
    """A horizontal marker band along a face from x = 0 to x = size (corner to
    corner). Its width is `taper` times the mid-face width at the corners and
    rises linearly to the full width in the middle; a few cracks cross it."""
    yy, xx = np.mgrid[0:size, 0:size].astype(float)
    frac = np.abs(xx / size - 0.5) * 2  # 0 mid-face, 1 at a corner
    w = width * (1 - (1 - taper) * frac)
    band = np.abs(yy - size / 2) <= w / 2
    for x in (180, 520, 700):  # cracks
        band[:, x : x + 6] = False
    return band


@pytest.mark.parametrize("taper", [1.0, 0.6])
def test_band_widths_read_how_a_marker_band_thins_toward_corners(taper: float) -> None:
    widths = band_widths_along(_marker_band(taper), (0.0, 450.0), (899.0, 450.0), reach_px=120)
    left, right = face_thinning(widths)
    # a quarter of the way along (0.2-0.3), frac = 0.4-0.6; the middle (0.4-0.6), frac 0-0.2
    expected = (1 - (1 - taper) * 0.5) / (1 - (1 - taper) * 0.1)
    assert left == pytest.approx(expected, abs=0.05)
    assert right == pytest.approx(expected, abs=0.05)


def test_band_widths_tell_a_thinning_band_from_a_uniform_one() -> None:
    """Negative control: a uniform band, cracks and all, must not read as thinning."""
    line = ((0.0, 450.0), (899.0, 450.0))
    uniform = face_thinning(band_widths_along(_marker_band(1.0), *line, reach_px=120))
    thinning = face_thinning(band_widths_along(_marker_band(0.7), *line, reach_px=120))
    assert all(v is not None and v > 0.95 for v in uniform)
    assert all(v is not None and v < 0.9 for v in thinning)
