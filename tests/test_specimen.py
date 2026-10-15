"""Specimen photo analysis, tested on synthetic photos of simulated slabs, where
the right answer is known (the owner's photos stay off the repository)."""

import io
import math
from functools import cache

import numpy as np
import pytest
from PIL import Image

from agatesim import _scipy
from agatesim.config import load_preset
from agatesim.criteria import evaluate
from agatesim.specimen.fit import replicate
from agatesim.specimen.identify import PASS_RELIABLE, SUPPORTED, identify
from agatesim.specimen.observe import Observation, observe, simplify
from agatesim.specimen.photo import load_photo
from agatesim.specimen.scale import Calibration, camera_height_mm, face_mm_per_px
from agatesim.specimen.segment import segment, trace_outline
from agatesim.specimen.synthetic import SyntheticPhoto, photograph
from agatesim.stats import band_statistics

PHOTO_RESOLUTION = 760


@cache
def _photo(preset: str) -> SyntheticPhoto:
    return photograph(load_preset(preset).with_resolution(PHOTO_RESOLUTION))


@cache
def _observe(preset: str) -> Observation:
    syn = _photo(preset)
    photo = load_photo(syn.jpeg)
    k = photo.scale_factor
    seg = segment(photo.rgb, (syn.centre[0] * k, syn.centre[1] * k))
    gravity: float = getattr(syn.result.config.model, "gravity_deg", 270.0)
    up = (gravity + 180) % 360
    return observe(photo.rgb, seg, syn.mm_per_px / k, up_deg=up)


def test_metadata_is_dropped_but_focal_length_is_read() -> None:
    exif = Image.Exif()
    exif[0x8769] = {0xA405: 26}  # FocalLengthIn35mmFilm
    exif[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0)}  # a GPS position
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (40, 60, 120)).save(buffer, format="JPEG", exif=exif)
    photo = load_photo(buffer.getvalue())
    assert photo.focal_35mm == 26
    again = Image.open(io.BytesIO(photo.png()))
    assert len(again.getexif()) == 0


def test_perspective_correction() -> None:
    """A camera ~206 mm above the ruler (iPhone 14, 26 mm-equivalent) makes a face
    22 mm higher look about 11% larger."""
    ruler = 25.4 / 373  # mm per px, from a 4032 × 3024 photo
    height = camera_height_mm(ruler, 26.0, (4032, 3024), 1.0)
    assert height == pytest.approx(206, rel=0.02)
    cal = Calibration(p1=(0, 0), p2=(373, 0), distance_mm=25.4, face_height_mm=22.2)
    face, used = face_mm_per_px(cal, 26.0, (4032, 3024))
    assert used == pytest.approx(height)
    assert face / ruler == pytest.approx((height - 22.2) / height)
    no_focal, none = face_mm_per_px(cal, None, (4032, 3024))
    assert none is None
    assert no_focal == pytest.approx(ruler)


def test_outline_tracing_and_simplifying() -> None:
    mask = np.zeros((40, 60), dtype=bool)
    mask[10:30, 15:45] = True
    outline = trace_outline(mask)
    assert len(outline) == 2 * (20 + 30) - 4  # every boundary pixel once
    corners = simplify(outline, 0.5)
    assert len(corners) == 4


@pytest.mark.parametrize("preset", ["fortification", "waterline", "quartz-geode"])
def test_segmentation_finds_the_slab(preset: str) -> None:
    """The traced face matches the slab (cavity plus a thin rim) within a few
    percent (the geode's dark crystal margin is the hardest), despite the shadow,
    the uneven light and the ruler."""
    syn = _photo(preset)
    obs = _observe(preset)
    rim = round(1.0 / syn.result.grid.dx)
    true_area = _scipy.dilate(syn.result.domain.mask, rim).sum() * syn.result.grid.dx**2
    found = obs.result.domain.mask.sum() * obs.result.grid.dx**2
    assert found == pytest.approx(true_area, rel=0.12)


def test_observed_band_thickness_matches_the_simulation() -> None:
    truth = band_statistics(_photo("waterline").result)
    seen = band_statistics(_observe("waterline").result)
    assert truth.thickness_median_mm is not None
    assert seen.thickness_median_mm == pytest.approx(truth.thickness_median_mm, rel=0.5)


@cache
def _perturbed(preset: str, quality: int) -> Observation:
    """A synthetic photo re-saved at a given JPEG quality, then observed."""
    syn = _photo(preset)
    buffer = io.BytesIO()
    Image.open(io.BytesIO(syn.jpeg)).save(buffer, format="JPEG", quality=quality)
    photo = load_photo(buffer.getvalue())
    k = photo.scale_factor
    seg = segment(photo.rgb, (syn.centre[0] * k, syn.centre[1] * k))
    gravity: float = getattr(syn.result.config.model, "gravity_deg", 270.0)
    return observe(photo.rgb, seg, syn.mm_per_px / k, up_deg=(gravity + 180) % 360)


@pytest.mark.parametrize("archetype", sorted(PASS_RELIABLE))
def test_photo_passes_are_never_false_positives(archetype: str) -> None:
    """The guard behind PASS_RELIABLE: on synthetic photos of every other form,
    at two JPEG qualities, the form is never wrongly confirmed."""
    for preset in SUPPORTED:
        if evaluate(archetype, _photo(preset).result).passed:
            continue  # the form is really there
        for quality in (95, 75):
            seen = evaluate(archetype, _perturbed(preset, quality).result)
            assert not seen.passed, f"{archetype} wrongly confirmed on a photo of {preset}"


def test_identification_reports_every_supported_form() -> None:
    found = identify(_observe("waterline").result)
    assert {i.archetype for i in found} == set(SUPPORTED)
    eye = next(i for i in found if i.archetype == "eye")
    assert not eye.pass_reliable
    assert all(
        i.verdict in {"confirmed", "not confirmed", "possible (unreliable test)"} for i in found
    )


def test_replica_matches_the_photo_statistics() -> None:
    obs = _observe("fortification")
    fit = replicate(obs.result)
    assert fit.config.cavity.outline is not None  # the specimen's own outline
    assert fit.target.thickness_median_mm is not None
    assert fit.stats.thickness_median_mm == pytest.approx(fit.target.thickness_median_mm, rel=0.35)
    assert math.isfinite(fit.mismatch)
