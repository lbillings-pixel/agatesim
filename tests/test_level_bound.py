"""Every Solid's level obeys the bound it reports (ADR 0076), so sphere tracing
[Nodule ADR 0005] never steps across the wall. Negative control: a level that
changes faster than its reported bound is caught."""

from dataclasses import dataclass

import numpy as np
import pytest

from agatesim.archetypes import Host
from agatesim.grid import FloatArray
from agatesim.volume.solids import (
    SOLID_PRESETS,
    BoolArray,
    LevelBound,
    Solid,
    extruded_outline,
    make_solid,
)


def _excess(solid: Solid, rng: np.random.Generator, n: int = 20000) -> float:
    """Largest |Δlevel| − (L·|Δp| + 2ε) over random nearby and distant pairs,
    inside and outside the solid; ≤ 0 means the bound held."""
    b = solid.level_bound()
    lo, hi = solid.bounds()
    pad = 0.2 * (hi - lo)
    p = lo - pad + (hi - lo + 2 * pad) * rng.random((n, 3))
    reach = np.exp(rng.uniform(np.log(1e-3), np.log(5.0), n))[:, None]  # 1 µm to 5 mm
    step = rng.standard_normal((n, 3))
    step *= reach / np.linalg.norm(step, axis=1, keepdims=True)
    q = np.concatenate([p + step, p[::-1]])
    p = np.concatenate([p, p])
    change = np.abs(solid.level(p) - solid.level(q))
    allowed = b.lipschitz * np.linalg.norm(p - q, axis=1) + 2 * b.error_mm
    return float((change - allowed).max())


@pytest.mark.parametrize("name", sorted(SOLID_PRESETS))
def test_each_solid_preset_obeys_its_level_bound(name: str) -> None:
    solid = make_solid(name, 40.0, yaw_deg=25.0, pitch_deg=10.0)
    assert _excess(solid, np.random.default_rng(0)) <= 1e-9


def test_a_drawn_solid_obeys_its_level_bound() -> None:
    outline = np.array([[-15, -8], [12, -10], [16, 4], [2, 12], [-12, 7.0]])
    solid = extruded_outline(outline, Host.VOLCANIC, 10.0)
    assert solid.level_bound().error_mm > 0  # its outline is sampled
    assert _excess(solid, np.random.default_rng(1)) <= 1e-9


@dataclass(frozen=True, eq=False)
class _Steeper(Solid):
    """Negative control: level grows 1.5× faster than the bound it reports."""

    inner: Solid

    @property
    def host(self) -> Host:  # pyright: ignore[reportIncompatibleVariableOverride]
        return self.inner.host

    def contains(self, points: FloatArray) -> BoolArray:
        return self.inner.contains(points)

    def level(self, points: FloatArray) -> FloatArray:
        return 1.5 * self.inner.level(points)

    def wall_distance(self, points: FloatArray) -> FloatArray:
        return self.inner.wall_distance(points)

    def support(self, direction: FloatArray) -> float:
        return self.inner.support(direction)

    def level_bound(self) -> LevelBound:
        return self.inner.level_bound()


def test_a_level_steeper_than_its_bound_is_caught() -> None:
    solid = _Steeper(make_solid(sorted(SOLID_PRESETS)[0], 40.0))
    assert _excess(solid, np.random.default_rng(0)) > 0.1
