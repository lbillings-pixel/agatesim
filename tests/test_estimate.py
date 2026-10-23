"""Rough cost estimates for the caution badge (ADR 0060): heavy where measured
runs were slow or large, light where they weren't."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agatesim import _rd, estimate
from agatesim.config import load_preset
from agatesim.models import FrontFeedback
from agatesim.server.app import create_app
from agatesim.volume.config import load_volume_preset


def test_h1_is_heavy_only_past_its_stiff_boundary() -> None:
    """Measured: about a second below the boundary, about fifty above it."""
    assert not estimate.run_2d(load_preset("fortification-mechanistic"), 768).heavy
    for stiff in (
        {"rejection": 2.0},
        {"trapping_velocity": 2.3},
        {"rejection": 1.55, "trapping_velocity": 1.25},
    ):
        assert estimate.h1_seconds(FrontFeedback.model_validate(stiff)) > estimate.HEAVY_SECONDS
    for calm in ({"rejection": 1.55, "trapping_velocity": 1.0}, {"trapping_velocity": 1.5}):
        assert estimate.h1_seconds(FrontFeedback.model_validate(calm)) < 5


def test_ordinary_actions_are_light() -> None:
    for name in ("fortification", "stick", "moss", "eye-mechanistic", "waterline-mechanistic"):
        assert not estimate.run_2d(load_preset(name), 512).heavy, name
    for name in ("fortification-mechanistic-3d", "moss-3d", "stick-mechanistic-3d"):
        config = load_volume_preset(name)
        assert not estimate.view_3d(config, 96, 384).heavy, name


def test_large_or_slow_actions_are_heavy() -> None:
    """Full runs at the largest sizes, H2 in 3D, long surveys, many settling pulses."""
    assert estimate.run_2d(load_preset("moss"), 4096).heavy
    h2 = estimate.view_3d(load_volume_preset("liesegang-nodule-3d"), 96, 384)
    assert h2.heavy
    assert any("H2 lattice" in r for r in h2.reasons)
    stick = load_volume_preset("stick-mechanistic-3d")
    assert estimate.survey_3d(stick, 100, 768).heavy
    settling = load_preset("waterline-mechanistic")
    long = {"pulses": 60, "pulse_interval": 10.0}
    many = settling.model_copy(update={"model": settling.model.model_copy(update=long)})
    assert estimate.run_2d(many, 256).heavy


def test_h2_without_a_gpu_is_far_heavier(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_preset("liesegang-nodule")
    monkeypatch.setattr(_rd, "gpu_in_use", lambda: True)
    gpu = estimate.run_2d(config, 256)
    monkeypatch.setattr(_rd, "gpu_in_use", lambda: False)
    cpu = estimate.run_2d(config, 256)
    assert cpu.seconds > 30 * gpu.seconds
    assert cpu.heavy
    assert any("no GPU" in r for r in cpu.reasons)


def test_the_estimate_endpoints(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path, static_dir=None)) as client:
        config = load_preset("fortification").model_dump(mode="json")
        two = client.post("/api/estimate", json={"config": config}).json()
        assert set(two) == {"preview", "run"}
        assert {"seconds", "memory_gb", "heavy", "reasons"} <= set(two["run"])
        volume = load_volume_preset("fortification-3d").model_dump(mode="json")
        three = client.post("/api/volume/estimate", json={"config": volume}).json()
        assert set(three) == {"view", "survey", "run"}


def test_fine_dendrites_are_light_on_the_cpu_with_numba(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0061: compiled, moss-fine-3d builds in about 19 s without a GPU (it
    took about 2 minutes); the NumPy loop alone is still heavy."""
    config = load_volume_preset("moss-fine-3d")
    monkeypatch.setattr(_rd, "gpu_in_use", lambda: False)
    monkeypatch.setattr(estimate.os, "cpu_count", lambda: 16)
    compiled = estimate.view_3d(config, 96, 384)
    assert 12 < compiled.seconds < 30
    assert not compiled.heavy

    def no_numba(name: str) -> None:
        return None

    monkeypatch.setattr(estimate.importlib.util, "find_spec", no_numba)
    reference = estimate.view_3d(config, 96, 384)
    assert reference.heavy
    assert any("no GPU" in r for r in reference.reasons)
