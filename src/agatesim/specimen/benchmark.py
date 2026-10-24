"""Hand-marked band boundaries: ground truth for the photo analysis (ADR 0019).

The owner draws a line across a photographed face and clicks each band boundary
along it. Comparing those marks with the boundaries the analysis traced along
the same line measures how well the tracing works on real photos, which
synthetic photos can't tell us.

Positions are kept as fractions t ∈ [0, 1] along the line, in the working
photo's pixels, so they don't depend on the analysis grid or the scale.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from agatesim.grid import FloatArray
from agatesim.specimen.observe import Observation

MIN_RUN_PX = 2  # traced runs shorter than this (analysis pixels) are slivers, not bands
MIN_TOLERANCE_MM = 0.1  # about how well a boundary can be clicked at full resolution
TOLERANCE_SHARE = 0.25  # of the median marked spacing
CHANCE_DRAWS = 200
TOLERANCES_MM = (0.2, 0.5)  # fixed tolerances for scoring in mm (ADR 0068 section 4)


class Transect(BaseModel):
    """A line drawn across the face and the band boundaries marked along it."""

    model_config = ConfigDict(extra="forbid")

    start: tuple[float, float] = Field(description="Working-photo px (x, y).")
    end: tuple[float, float] = Field(description="Working-photo px (x, y).")
    boundaries: list[float] = Field(default=[], description="Marks, as t along the line.")


@dataclass(frozen=True)
class TransectScore:
    marked: int
    traced: int
    matched: int
    missed: int  # marked boundaries the analysis didn't find
    extra: int  # traced boundaries with no mark nearby
    precision: float | None  # matched / traced
    recall: float | None  # matched / marked
    mean_offset_mm: float | None
    tolerance_mm: float
    # The recall as many boundaries placed at random (between the first and last
    # mark) would get: closely spaced marks are easy to hit by chance.
    chance_recall: float | None = None

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def _to_world(obs: Observation, x: float, y: float) -> FloatArray:
    cx, cy = obs.centre_px
    return np.array([(x - cx) * obs.mm_per_px, (cy - y) * obs.mm_per_px])


def traced_boundaries(obs: Observation, transect: Transect) -> list[float]:
    """Where the traced band changes along the line, as t; changes into or out of
    open space and the host count too (a boundary the owner would also see)."""
    p0 = _to_world(obs, *transect.start)
    p1 = _to_world(obs, *transect.end)
    length = float(np.linalg.norm(p1 - p0))
    grid = obs.result.grid
    if length <= 0:
        return []
    count = max(int(np.ceil(2 * length / grid.dx)), 2)
    t = np.linspace(0.0, 1.0, count)
    points = p0[None, :] + t[:, None] * (p1 - p0)[None, :]
    band, valid = grid.sample(obs.result.fields.band, points)
    inside, _ = grid.sample(obs.result.domain.mask, points)
    labels = np.where(valid & inside.astype(bool), band, -2)
    starts = np.flatnonzero(np.r_[True, labels[1:] != labels[:-1]])
    min_t = MIN_RUN_PX * grid.dx / length
    out: list[float] = []
    for k in range(1, len(starts)):
        end = starts[k + 1] if k + 1 < len(starts) else len(t)
        if float(t[end - 1] - t[starts[k]]) < min_t and end < len(t):
            continue  # a sliver: not a band of its own
        if labels[starts[k]] == -2 and labels[starts[k] - 1] == -2:
            continue
        out.append(float(0.5 * (t[starts[k]] + t[starts[k] - 1])))
    return out


def score(marked_mm: FloatArray, traced_mm: FloatArray) -> TransectScore:
    """One-to-one matching of traced to marked positions (mm along the line),
    closest pairs first, within a tolerance: a quarter of the median marked
    spacing, at least 0.2 mm."""
    marked_mm = np.sort(np.asarray(marked_mm, dtype=np.float64))
    traced_mm = np.sort(np.asarray(traced_mm, dtype=np.float64))
    spacing = float(np.median(np.diff(marked_mm))) if len(marked_mm) > 1 else 0.0
    tolerance = max(MIN_TOLERANCE_MM, TOLERANCE_SHARE * spacing)
    matched, offsets = _match(marked_mm, traced_mm, tolerance)
    chance = None
    if len(marked_mm):
        rng = np.random.default_rng(0)
        lo, hi = float(marked_mm[0]), float(marked_mm[-1])
        hits = [
            _match(marked_mm, rng.uniform(lo, hi, len(traced_mm)), tolerance)[0]
            for _ in range(CHANCE_DRAWS)
        ]
        chance = float(np.mean(hits)) / len(marked_mm)
    return TransectScore(
        marked=len(marked_mm),
        traced=len(traced_mm),
        matched=matched,
        missed=len(marked_mm) - matched,
        extra=len(traced_mm) - matched,
        precision=matched / len(traced_mm) if len(traced_mm) else None,
        recall=matched / len(marked_mm) if len(marked_mm) else None,
        mean_offset_mm=float(np.mean(offsets)) if offsets else None,
        tolerance_mm=tolerance,
        chance_recall=chance,
    )


def _match(
    marked_mm: FloatArray, traced_mm: FloatArray, tolerance: float
) -> tuple[int, list[float]]:
    pairs = sorted(
        (abs(m - s), i, j)
        for i, m in enumerate(marked_mm)
        for j, s in enumerate(traced_mm)
        if abs(m - s) <= tolerance
    )
    used_m: set[int] = set()
    used_t: set[int] = set()
    offsets: list[float] = []
    for d, i, j in pairs:
        if i in used_m or j in used_t:
            continue
        used_m.add(i)
        used_t.add(j)
        offsets.append(d)
    return len(offsets), offsets


@dataclass(frozen=True)
class FixedScore:
    """Precision, recall and F within a fixed tolerance in mm (ADR 0068
    section 4), beside the same for shuffled boundaries: the found boundaries'
    gaps in a random order, at a random offset, wrapped within the line's
    marked and found span. Shuffling keeps how many there are and how they
    are spaced, so only their positions are tested."""

    tolerance_mm: float
    marked: int
    found: int
    matched: int
    chance_matched: float  # mean over CHANCE_DRAWS shuffles

    @property
    def precision(self) -> float | None:
        return self.matched / self.found if self.found else None

    @property
    def recall(self) -> float | None:
        return self.matched / self.marked if self.marked else None

    @property
    def f(self) -> float | None:
        return _f(self.matched, self.marked, self.found)

    @property
    def chance_f(self) -> float | None:
        return _f(self.chance_matched, self.marked, self.found)


def _f(matched: float, marked: int, found: int) -> float | None:
    """F (the harmonic mean of precision and recall) = 2 matched / (marked + found)."""
    return 2 * matched / (marked + found) if marked + found else None


def shuffled(found_mm: FloatArray, lo: float, hi: float, rng: np.random.Generator) -> FloatArray:
    """Found boundaries with their gaps shuffled and the run shifted at random,
    wrapped within [lo, hi]."""
    found_mm = np.sort(np.asarray(found_mm, dtype=np.float64))
    if len(found_mm) == 0 or hi <= lo:
        return found_mm
    gaps = rng.permutation(np.diff(found_mm))
    run = np.concatenate([[0.0], np.cumsum(gaps)])
    return lo + (rng.uniform(0.0, hi - lo) + run) % (hi - lo)


def score_fixed(
    marked_mm: FloatArray, found_mm: FloatArray, tolerance_mm: float, seed: int = 0
) -> FixedScore:
    marked_mm = np.sort(np.asarray(marked_mm, dtype=np.float64))
    found_mm = np.sort(np.asarray(found_mm, dtype=np.float64))
    matched, _ = _match(marked_mm, found_mm, tolerance_mm)
    both = np.concatenate([marked_mm, found_mm])
    chance = 0.0
    if len(marked_mm) and len(found_mm):
        rng = np.random.default_rng(seed)
        lo, hi = float(both.min()), float(both.max())
        draws = [
            _match(marked_mm, shuffled(found_mm, lo, hi, rng), tolerance_mm)[0]
            for _ in range(CHANCE_DRAWS)
        ]
        chance = float(np.mean(draws))
    return FixedScore(tolerance_mm, len(marked_mm), len(found_mm), matched, chance)


def pooled(scores: list[FixedScore]) -> FixedScore:
    """Several lines' scores at one tolerance, counted together."""
    return FixedScore(
        scores[0].tolerance_mm,
        sum(s.marked for s in scores),
        sum(s.found for s in scores),
        sum(s.matched for s in scores),
        sum(s.chance_matched for s in scores),
    )


def compare(obs: Observation, transect: Transect) -> tuple[list[float], TransectScore]:
    """The traced boundaries along a transect (as t) and their score against the marks."""
    traced = traced_boundaries(obs, transect)
    return traced, score_along(obs, transect, traced)


def score_along(obs: Observation, transect: Transect, found: list[float]) -> TransectScore:
    """Score boundaries found along a transect (as t) against its marks."""
    p0 = _to_world(obs, *transect.start)
    p1 = _to_world(obs, *transect.end)
    length = float(np.linalg.norm(p1 - p0))
    marked_mm = np.array(transect.boundaries, dtype=np.float64) * length
    return score(marked_mm, np.array(found, dtype=np.float64) * length)
