"""Prepare a 3D run, then evaluate it as a volume or as cuts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agatesim.fields import Fields, Phase
from agatesim.volume.config import SliceConfig, VolumeConfig
from agatesim.volume.grid import Grid3
from agatesim.volume.models import Evaluator, Setting, prepare
from agatesim.volume.slicing import Cut, Plane, cut
from agatesim.volume.solids import BoolArray, Solid


@dataclass(frozen=True, eq=False)
class VolumeResult:
    grid: Grid3
    fields: Fields  # arrays shaped grid.shape
    inside: BoolArray  # True inside the cavity


@dataclass(frozen=True, eq=False)
class VolumeSimulation:
    """A prepared 3D run: the model's whole-cavity history is computed; fields
    come from evaluating it at points."""

    config: VolumeConfig
    setting: Setting
    evaluate: Evaluator

    @property
    def solid(self) -> Solid:
        return self.setting.solid

    def grid(self, resolution: int | None = None) -> Grid3:
        lo, hi = self.setting.solid.bounds()
        res = self.config.grid.resolution if resolution is None else resolution
        return Grid3.around(lo, hi, res, self.config.grid.margin_fraction)

    def volume(self, resolution: int | None = None) -> VolumeResult:
        grid = self.grid(resolution)
        shape = grid.shape
        phase = np.full(shape, Phase.HOST, dtype=np.uint8)
        band = np.full(shape, -1, dtype=np.int32)
        impurity = np.zeros(shape, dtype=np.float32)
        translucency = np.zeros(shape, dtype=np.float32)
        t_dep = np.full(shape, np.nan, dtype=np.float32)
        grain = np.full(shape, -1, dtype=np.int32)
        micro = np.full(shape, np.nan, dtype=np.float32)
        inside = np.zeros(shape, dtype=bool)
        for layers, points in grid.chunks():
            ins = self.setting.solid.contains(points)
            f = self.evaluate(points, ins)
            part = (layers.stop - layers.start, grid.ny, grid.nx)
            phase[layers] = f.phase.reshape(part)
            band[layers] = f.band.reshape(part)
            impurity[layers] = f.impurity.reshape(part)
            translucency[layers] = f.translucency.reshape(part)
            t_dep[layers] = f.t_dep.reshape(part)
            grain[layers] = f.grain.reshape(part)
            micro[layers] = f.micro_spacing_um.reshape(part)
            inside[layers] = ins.reshape(part)
        fields = Fields(
            phase=phase,
            band=band,
            impurity=impurity,
            translucency=translucency,
            t_dep=t_dep,
            grain=grain,
            micro_spacing_um=micro,
        )
        return VolumeResult(grid=grid, fields=fields, inside=inside)

    def plane(self, slice_config: SliceConfig | None = None) -> Plane:
        return Plane.of(slice_config or self.config.slice, self.setting.solid.centre())

    def cut(self, slice_config: SliceConfig | None = None) -> Cut:
        config = self.config if slice_config is None else self.config.with_slice(slice_config)
        return cut(config, self.setting, self.evaluate, self.plane(config.slice))

    def cut_plane(self, plane: Plane, resolution: int | None = None) -> Cut:
        config = self.config
        if resolution is not None:
            config = config.with_slice(config.slice.model_copy(update={"resolution": resolution}))
        return cut(config, self.setting, self.evaluate, plane)


def prepare_volume(config: VolumeConfig) -> VolumeSimulation:
    rng = np.random.default_rng(config.seed)
    solid = config.solid.build()
    setting = Setting.build(solid, config.gravity.vector())
    return VolumeSimulation(
        config=config, setting=setting, evaluate=prepare(config.model, setting, rng)
    )
