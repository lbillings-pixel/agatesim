"""Mechanistic H2 (Liesegang): its laws, its lattice independence, and the
hypothesis test it was built for, sharp corners."""

from __future__ import annotations

from functools import cache

import numpy as np
import pytest

from agatesim import _rd
from agatesim.config import RunConfig, load_preset
from agatesim.criteria import evaluate
from agatesim.simulate import SimulationResult, simulate


def _config(
    size_mm: float, lattice_mm: float, resolution: int, preset: str = "nodule-angular"
) -> RunConfig:
    return RunConfig.model_validate(
        {
            "name": "h2",
            "archetype": "fortification",
            "grid": {"resolution": resolution},
            "cavity": {"preset": preset, "size_mm": size_mm},
            "model": {"kind": "mechanistic-liesegang", "lattice_mm": lattice_mm},
        }
    )


@cache
def _angular() -> SimulationResult:
    return simulate(_config(15.0, 0.04, 512))


def test_liesegang_bands_are_closed_rings_that_round_off_the_corners() -> None:
    """The hypothesis test: diffusion-controlled precipitation gives closed,
    wall-parallel rings, but not fortification's sharp corners
    ([@cartwright2026] §5.1.1). The front-feedback model keeps them (ADR 0013)."""
    ev = {r.id: r for r in evaluate("fortification", _angular()).results}
    assert ev["closed-bands"].passed
    assert ev["band-count"].passed
    assert not ev["corners-preserved"].passed
    assert ev["corners-preserved"].value is not None
    assert ev["corners-preserved"].value > 1.0  # rounded well beyond the threshold (0.7)


def test_band_spacing_grows_inward() -> None:
    """The Liesegang spacing law: band positions in a geometric series, so each
    cycle (a precipitate band and the clear gel after it) is wider than the last."""
    result = _angular()
    d = result.domain.wall_distance
    band = result.fields.band
    mask = result.domain.mask
    starts = np.sort([float(np.min(d[mask & (band == k)])) for k in np.unique(band[mask])])
    cycles = starts[3::2] - starts[1:-2:2]  # after the first, merged near-wall band
    assert len(cycles) >= 3
    assert np.all(np.diff(cycles) > 0)


def test_output_resolution_does_not_change_the_pattern() -> None:
    """The kinetics run on a lattice fixed in millimetres, so a preview shows the
    same bands as a full run."""
    coarse = simulate(_config(10.0, 0.05, 192))
    fine = simulate(_config(10.0, 0.05, 384))
    assert len(np.unique(coarse.fields.band[coarse.domain.mask])) == len(
        np.unique(fine.fields.band[fine.domain.mask])
    )


def test_liesegang_reproduces_seam_agate(monkeypatch: pytest.MonkeyPatch) -> None:
    """In a crack, Liesegang bands mirror each other about the midline (ADR 0015).
    Needs a resolved lattice, so it runs only where a GPU is available."""
    if _rd.array_module(prefer_gpu=True) is np:
        pytest.skip("needs the GPU backend (CuPy) to run at a resolved lattice")
    monkeypatch.setenv("AGATESIM_GPU", "1")
    ev = evaluate("seam", simulate(load_preset("liesegang-seam")))
    assert ev.passed, [r for r in ev.results if not r.passed]


def test_gpu_matches_cpu() -> None:
    xp = _rd.array_module(prefer_gpu=True)
    if xp is np:
        pytest.skip("no GPU backend (CuPy) available")
    inside = np.zeros((60, 60), dtype=bool)
    inside[5:55, 5:55] = True
    kwargs = {
        "a0": 20.0, "d_b": 0.5, "d_c": 0.5, "rate": 0.005, "nucleation": 0.35,
        "spreading": 0.3, "solubility": 0.1, "growth": 0.05, "deepest": (30, 30),
        "max_steps": 3000,
    }  # fmt: skip
    p_cpu, t_cpu, _ = _rd.liesegang(np, inside, **kwargs)  # type: ignore[arg-type]
    p_gpu, t_gpu, _ = _rd.liesegang(xp, inside, **kwargs)  # type: ignore[arg-type]
    np.testing.assert_allclose(p_gpu, p_cpu, rtol=1e-6, atol=1e-9)
    np.testing.assert_allclose(t_gpu, t_cpu, equal_nan=True)


def test_a_cavity_the_front_fills_at_once_gives_one_band() -> None:
    """A cavity a few lattice cells across fills before the first record of the
    front's arrival, so every cell arrives together: one band, not a crash."""
    from agatesim.models.liesegang import bands_by_arrival

    inside = np.ones(50, dtype=bool)
    band = bands_by_arrival(np.full(50, 0.3), inside.copy(), inside, min_cells=4)
    assert (band == 0).all()
    result = simulate(_config(3.0, 0.25, 64))
    assert result.fields.band[result.domain.mask].max() == 0
