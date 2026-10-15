"""Run a configured simulation."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from agatesim.config import RunConfig
from agatesim.fields import Fields, Phase
from agatesim.grid import FloatArray, Grid
from agatesim.models import (
    Domain,
    FrontFeedback,
    ProceduralFortification,
    ProceduralGrowth,
    ProceduralWaterline,
    run_fortification,
    run_front_feedback,
    run_growth,
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
        if isinstance(self.config.model, ProceduralWaterline | ProceduralGrowth):
            return self.config.model.gravity()
        th = np.radians(DEFAULT_GRAVITY_DEG)
        return np.array([np.cos(th), np.sin(th)])


def simulate(config: RunConfig) -> SimulationResult:
    rng = np.random.default_rng(config.seed)
    cavity = config.cavity.build()
    grid = Grid.around(cavity.bounds(), config.grid.resolution, config.grid.margin_fraction)
    domain = Domain.build(cavity, grid, config.cavity.tube_array())
    model = config.model
    match model:
        case ProceduralFortification():
            fields = run_fortification(model, domain, rng)
        case ProceduralWaterline():
            fields = run_waterline(model, domain, rng)
        case ProceduralGrowth():
            fields = run_growth(model, domain, rng)
        case FrontFeedback():
            fields = run_front_feedback(model, domain, rng)
    return SimulationResult(config=config, domain=domain, fields=_with_inclusions(fields, domain))


def _with_inclusions(fields: Fields, domain: Domain) -> Fields:
    """Mark tube filaments. The growth model grows around them; the older
    single-form models ignore them, so this only paints them in."""
    inc = domain.inclusions
    if inc is None or not inc.any():
        return fields
    phase = fields.phase.copy()
    phase[inc] = Phase.INCLUSION
    return replace(
        fields,
        phase=phase,
        band=np.where(inc, -1, fields.band).astype(np.int32),
        t_dep=np.where(inc, np.nan, fields.t_dep).astype(np.float32),
        grain=np.where(inc, -1, fields.grain).astype(np.int32),
        translucency=np.where(inc, 0.0, fields.translucency).astype(np.float32),
        # Tint 0: filament cores are reported as Fe-silicates such as celadonite.
        impurity=np.where(inc, 0.0, fields.impurity).astype(np.float32),
        micro_spacing_um=np.where(inc, np.nan, fields.micro_spacing_um).astype(np.float32),
    )
