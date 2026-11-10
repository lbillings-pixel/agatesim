"""Runs and photos that several test files use, made once per session (audit B5).

Everything here is shared, so tests must only read it: copy before changing an
array in place.
"""

from __future__ import annotations

from functools import cache

from agatesim.config import load_preset
from agatesim.simulate import SimulationResult, simulate
from agatesim.specimen.synthetic import SyntheticPhoto, photograph

# Full-size runs read by more than one test file. Only these are kept (tens of MB
# each); keeping every preset's full run would hold about a gigabyte.
SHARED_RUNS = frozenset(
    {
        "fortification-mechanistic",
        "iris-mechanistic",
        "liesegang-nodule",
        "waterline",
        "waterline-mechanistic",
    }
)


def preset_run(name: str) -> SimulationResult:
    """A preset's full-size run: made once if several files read it."""
    return _kept_run(name) if name in SHARED_RUNS else simulate(load_preset(name))


@cache
def _kept_run(name: str) -> SimulationResult:
    return simulate(load_preset(name))


@cache
def preset_photo(name: str, resolution: int = 760) -> SyntheticPhoto:
    """A synthetic photo of a preset's run (760 px: the size the specimen gate
    was validated at)."""
    return photograph(load_preset(name).with_resolution(resolution))
