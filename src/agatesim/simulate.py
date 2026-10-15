"""Run a configured simulation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agatesim.config import RunConfig
from agatesim.fields import Fields
from agatesim.geometry import make_cavity
from agatesim.grid import FloatArray, Grid
from agatesim.models import (
    Domain,
    ProceduralFortification,
    ProceduralWaterline,
    run_fortification,
    run_waterline,
)

DEFAULT_GRAVITY_DEG = 270.0


@dataclass(frozen=True)
class SimulationResult:
    config: RunConfig
    domain: Domain
    fields: Fields

    @property
    def grid(self) -> Grid:
        return self.domain.grid

    @property
    def gravity(self) -> FloatArray:
        """Unit gravity vector; models without gravity are taken as formed upright."""
        if isinstance(self.config.model, ProceduralWaterline):
            return self.config.model.gravity()
        th = np.radians(DEFAULT_GRAVITY_DEG)
        return np.array([np.cos(th), np.sin(th)])


def simulate(config: RunConfig) -> SimulationResult:
    rng = np.random.default_rng(config.seed)
    cavity = make_cavity(config.cavity.preset, config.cavity.size_mm, config.cavity.rotation_deg)
    grid = Grid.around(cavity.bounds(), config.grid.resolution, config.grid.margin_fraction)
    domain = Domain.build(cavity, grid)
    model = config.model
    match model:
        case ProceduralFortification():
            fields = run_fortification(model, domain, rng)
        case ProceduralWaterline():
            fields = run_waterline(model, domain, rng)
    return SimulationResult(config=config, domain=domain, fields=fields)
