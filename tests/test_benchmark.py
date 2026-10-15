"""Hand-marked band boundaries as ground truth for the photo analysis."""

from __future__ import annotations

import numpy as np

from agatesim.config import load_preset
from agatesim.specimen.benchmark import Transect, compare, score
from agatesim.specimen.observe import observe
from agatesim.specimen.photo import load_photo
from agatesim.specimen.segment import segment
from agatesim.specimen.synthetic import photograph


def test_score_matches_one_to_one_within_tolerance() -> None:
    marked = np.array([1.0, 2.0, 3.0, 4.0])
    traced = np.array([1.05, 1.1, 2.02, 3.6, 5.0])  # two near 1.0, one too far from 3.0
    s = score(marked, traced)
    assert s.tolerance_mm == 0.25  # a quarter of the 1 mm spacing
    assert (s.matched, s.missed, s.extra) == (2, 2, 3)
    assert s.recall == 0.5
    assert s.mean_offset_mm is not None
    assert abs(s.mean_offset_mm - 0.035) < 1e-9


def test_true_boundaries_marked_on_a_synthetic_photo_are_found() -> None:
    """Marks placed exactly where the simulated bands change, along a line from
    the centre toward the wall, as the owner would click them. The analysis
    should find most of them, and few that aren't there."""
    syn = photograph(load_preset("fortification").with_resolution(760))
    photo = load_photo(syn.jpeg)
    assert photo.scale_factor == 1.0  # working photo = synthetic photo pixels
    seg = segment(photo.rgb, syn.centre)
    obs = observe(photo.rgb, seg, syn.mm_per_px)
    # The true band field along the line (the slab is pasted at 1 px per grid pixel).
    grid = syn.result.grid
    cx, cy = syn.centre
    start, end = (cx, cy), (cx + 0.45 * grid.shape[1], cy)
    t = np.linspace(0, 1, 4000)
    xs = start[0] + t * (end[0] - start[0])
    cols = (xs - (cx - grid.shape[1] / 2)).astype(int)
    rows = np.full_like(cols, int(cy - (syn.centre[1] - grid.shape[0] / 2)))
    inside = syn.result.domain.mask[rows, cols]
    band = np.where(inside, syn.result.fields.band[rows, cols], -2)
    change = np.flatnonzero(band[1:] != band[:-1])
    marks = [float(0.5 * (t[i] + t[i + 1])) for i in change]
    transect = Transect(start=start, end=end, boundaries=marks)
    _, s = compare(obs, transect)
    assert s.marked >= 15
    assert s.recall is not None
    assert s.precision is not None
    assert s.recall > 0.6
    assert s.precision > 0.6
