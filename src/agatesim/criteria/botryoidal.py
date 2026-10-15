"""Criteria for botryoidal and eye agate: banding that radiates from nucleation
sites on the growth surface (criteria.radial)."""

from __future__ import annotations

import numpy as np

from agatesim import _scipy
from agatesim.criteria.common import band_boundaries
from agatesim.criteria.radial import growth_centres, isochrons, near_phase, wall_distance_of
from agatesim.criteria.types import Measurement
from agatesim.fields import Phase
from agatesim.simulate import SimulationResult

FRONT_PX = 7  # the final growth surface: chalcedony this close to the open space
WALL_PX = 8  # the first growth: chalcedony this close to the host rock
CENTRE_VOTES = 0.01  # share of voting pixels a growth centre needs
WALL_TOLERANCE = 0.03  # of cavity size


def _fraction(numerator: np.ndarray, denominator: np.ndarray) -> float:
    return float(numerator.sum()) / max(int(denominator.sum()), 1)


def lobate_front(result: SimulationResult) -> Measurement:
    """Share of the final growth surface (next to the open space) whose growth
    surfaces bulge into the open space, radiating from a centre behind them."""
    if not (result.fields.phase == Phase.VOID).any():
        return None, "no open space, so the final growth surface isn't exposed"
    iso = isochrons(result)
    front = near_phase(result, Phase.VOID, FRONT_PX) & iso.valid
    if not front.any():
        return None, "no banding next to the open space"
    return _fraction(front & iso.diverging, front), f"{int(front.sum())} surface pixels"


def lobe_count(result: SimulationResult) -> Measurement:
    """Separate bulging stretches of the final growth surface, divided by cusps
    (each holding at least 1% of the surface)."""
    if not (result.fields.phase == Phase.VOID).any():
        return None, "no open space, so the final growth surface isn't exposed"
    iso = isochrons(result)
    zone = near_phase(result, Phase.VOID, FRONT_PX) & (result.fields.phase == Phase.CHALCEDONY)
    front = zone & iso.valid
    # Judge bulging over a short stretch of surface, so isolated noisy pixels
    # don't split a lobe; cusps (where no isochron is defined) still divide them.
    sigma = 2.0
    valid = _scipy.gaussian(front.astype(np.float64), sigma)
    share = _scipy.gaussian((front & iso.diverging).astype(np.float64), sigma) / np.maximum(
        valid, 1e-9
    )
    lobe = zone & (valid > 0.25) & (share > 0.5)
    labels = _scipy.label(lobe, eight_connected=True)
    sizes = np.bincount(labels.ravel())[1:]
    lobes = int((sizes >= CENTRE_VOTES * max(int(zone.sum()), 1)).sum())
    return lobes, f"{lobes} lobes"


def bands_follow_lobes(result: SimulationResult) -> Measurement:
    """Share of band boundaries that curve about a centre behind them, as bands
    concentric about the lobes do."""
    iso = isochrons(result)
    bb = band_boundaries(result) & iso.valid
    if not bb.any():
        return None, "no band boundaries"
    return _fraction(bb & iso.diverging, bb), f"{int(bb.sum())} band-boundary pixels"


def evaluate_botryoidal(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "lobate-front": lobate_front(result),
        "lobe-count": lobe_count(result),
        "bands-follow-lobes": bands_follow_lobes(result),
    }


def _eye_centres(result: SimulationResult) -> tuple[list[tuple[float, float]], int]:
    iso = isochrons(result)
    bb = band_boundaries(result)
    centres = growth_centres(result, iso, bb, CENTRE_VOTES)
    return [(c.x, c.y) for c in centres], int((bb & iso.valid).sum())


def discrete_eyes(result: SimulationResult) -> Measurement:
    """Number of separate centres that banding radiates from."""
    centres, n = _eye_centres(result)
    return len(centres), f"{len(centres)} centres from {n} band-boundary pixels"


def wall_nucleated(result: SimulationResult) -> Measurement:
    """Share of growth centres lying on the original cavity wall."""
    centres, _ = _eye_centres(result)
    if not centres:
        return 0.0, "no growth centres"
    d = wall_distance_of(result, np.array(centres)) / result.domain.cavity.size_mm
    on_wall = int((d <= WALL_TOLERANCE).sum())
    return on_wall / len(centres), f"{on_wall} of {len(centres)} centres on the wall"


def isolated_eyes(result: SimulationResult) -> Measurement:
    """Share of the first growth on the wall that is ordinary layering rather than
    radiating eye bands: the eyes are separate, not a continuous crust."""
    iso = isochrons(result)
    first = near_phase(result, Phase.HOST, WALL_PX) & iso.valid
    if not first.any():
        return None, "no banding on the wall"
    return 1 - _fraction(first & iso.diverging, first), f"{int(first.sum())} wall pixels"


def evaluate_eye(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "discrete-eyes": discrete_eyes(result),
        "wall-nucleated": wall_nucleated(result),
        "isolated-eyes": isolated_eyes(result),
    }
