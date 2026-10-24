"""Hand-marked band boundaries as ground truth for the photo analysis."""

from __future__ import annotations

import numpy as np

from agatesim.config import load_preset
from agatesim.specimen.benchmark import (
    Transect,
    compare,
    pooled,
    score,
    score_along,
    score_fixed,
    shuffled,
)
from agatesim.specimen.edges import boundary_edges, edge_crossings
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
    assert s.chance_recall is not None
    assert s.recall > 2 * s.chance_recall

    # The full-resolution boundary detector finds them too.
    edges = boundary_edges(photo.rgb, seg.mask, 1.0)
    e = score_along(obs, transect, edge_crossings(edges, transect))
    assert e.recall is not None
    assert e.precision is not None
    assert e.chance_recall is not None
    assert e.recall > 0.6
    assert e.precision > 0.6
    assert e.recall > 1.5 * e.chance_recall


def test_chance_recall_grows_with_the_number_of_guesses() -> None:
    marked = np.arange(0.0, 10.0, 0.5)
    few = score(marked, np.array([3.0]))
    many = score(marked, np.linspace(0.1, 9.4, 40))
    assert few.chance_recall is not None
    assert many.chance_recall is not None
    assert few.chance_recall <= 1 / len(marked)
    assert many.chance_recall > 0.3
    assert score(marked, np.array([])).chance_recall == 0.0


def test_shuffling_keeps_the_count_and_the_gaps() -> None:
    found = np.array([1.0, 1.3, 2.0, 2.2, 3.5])
    out = shuffled(found, 0.0, 5.0, np.random.default_rng(1))
    assert len(out) == len(found)
    assert np.all((out >= 0.0) & (out < 5.0))
    # Round the 5 mm loop the gaps are the same ones in another order, plus the
    # one closing the loop.
    loop = np.sort(out)
    gaps = np.diff(np.concatenate([loop, [loop[0] + 5.0]]))
    expected = np.concatenate([np.diff(found), [5.0 - (found[-1] - found[0])]])
    assert np.allclose(np.sort(gaps), np.sort(expected))


def test_fixed_tolerance_scores_beat_shuffles_only_when_positions_are_right() -> None:
    rng = np.random.default_rng(0)
    marks = np.cumsum(rng.uniform(0.3, 1.2, 40))
    exact = score_fixed(marks, marks + rng.normal(0, 0.05, 40), 0.2)
    assert exact.f is not None
    assert exact.f > 0.9
    assert exact.chance_f is not None
    assert exact.chance_f < 0.5
    # Negative control: boundaries at random positions score near the shuffles.
    guess = score_fixed(marks, np.sort(rng.uniform(marks[0], marks[-1], 40)), 0.2)
    assert guess.f is not None
    assert guess.chance_f is not None
    assert abs(guess.f - guess.chance_f) < 0.15
    # A wider tolerance finds more, by chance too.
    wide = score_fixed(marks, np.sort(rng.uniform(marks[0], marks[-1], 40)), 0.5)
    assert wide.chance_f is not None
    assert wide.chance_f > guess.chance_f


def test_pooled_scores_count_lines_together() -> None:
    a = score_fixed(np.array([1.0, 2.0]), np.array([1.05]), 0.2)
    b = score_fixed(np.array([1.0, 2.0, 3.0]), np.array([2.0, 3.0, 9.0]), 0.2)
    p = pooled([a, b])
    assert (p.marked, p.found, p.matched) == (5, 4, 3)
    assert p.f == 2 * 3 / 9
    assert score_fixed(np.array([]), np.array([]), 0.2).f is None
