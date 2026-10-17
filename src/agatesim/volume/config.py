"""Configuration of a 3D run, read from TOML."""

from __future__ import annotations

import hashlib
import json
import tomllib
from importlib import resources
from pathlib import Path
from typing import Annotated

import numpy as np
import tomli_w
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from agatesim.archetypes import Host, load_registry
from agatesim.geometry import MAX_OUTLINE_POINTS, MIN_OUTLINE_POINTS, drawn_cavity
from agatesim.grid import FloatArray
from agatesim.models import (
    FrontFeedback,
    Liesegang,
    ProceduralFortification,
    ProceduralGrowth,
    ProceduralWaterline,
    Settling,
    Staged,
)
from agatesim.volume.growth import unsupported_in_3d
from agatesim.volume.models import gravity_vector
from agatesim.volume.solids import (
    SOLID_PRESETS,
    Rotated,
    Solid,
    extruded_outline,
    make_solid,
    rotation,
)

VolumeModelConfig = Annotated[
    ProceduralFortification
    | ProceduralWaterline
    | ProceduralGrowth
    | FrontFeedback
    | Liesegang
    | Settling
    | Staged,
    Field(discriminator="kind"),
]
DEFAULT_GRAVITY_DEG = 270.0


class VolumeGridConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resolution: int = Field(
        default=160, ge=16, le=384, description="Voxels along the longest side."
    )
    margin_fraction: float = Field(default=0.04, ge=0, le=0.5, description="Host-rock border.")


class FilamentConfig(BaseModel):
    """A thin straight filament in the cavity (a tube agate seed), from one end to
    the other, in mm from the cavity's centre."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_mm: tuple[float, float, float]
    end_mm: tuple[float, float, float]
    radius_mm: float = Field(default=0.3, gt=0, le=10, description="Filament radius.")


class SolidConfig(BaseModel):
    """A preset solid, or a drawn outline extruded into a slab-like solid. Exactly
    one of `preset` and `outline` is given."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    preset: str | None = None
    outline: (
        Annotated[
            list[tuple[float, float]],
            Field(min_length=MIN_OUTLINE_POINTS, max_length=MAX_OUTLINE_POINTS),
        ]
        | None
    ) = Field(default=None, description="Drawn outline (any units; only the shape is used).")
    host: Host | None = Field(default=None, description="Host setting of a drawn outline.")
    smooth: bool = Field(default=False, description="Smooth a drawn outline.")
    depth_fraction: float = Field(
        default=0.6, gt=0, le=2, description="Depth of an extruded outline, × its longest side."
    )
    size_mm: float = Field(default=50.0, gt=0, le=500, description="Longest dimension.")
    yaw_deg: float = Field(default=0.0, description="Turn about the vertical axis.")
    pitch_deg: float = Field(default=0.0, description="Tilt of the long axis up from horizontal.")
    filaments: list[FilamentConfig] = Field(default_factory=list[FilamentConfig], max_length=200)

    @field_validator("preset")
    @classmethod
    def _known_preset(cls, v: str | None) -> str | None:
        if v is not None and v not in SOLID_PRESETS:
            raise ValueError(f"unknown solid preset {v!r}; choose from {sorted(SOLID_PRESETS)}")
        return v

    @model_validator(mode="after")
    def _one_shape(self) -> SolidConfig:
        if (self.preset is None) == (self.outline is None):
            raise ValueError("give exactly one of `preset` and `outline`")
        if self.outline is not None and self.host is None:
            raise ValueError("a drawn `outline` needs a `host` (volcanic, sedimentary or seam)")
        if self.outline is None and (self.host is not None or self.smooth):
            raise ValueError("`host` and `smooth` apply only to a drawn `outline`")
        solid = self.build()  # raises ValueError for a bad outline
        for i, fil in enumerate(self.filaments):
            mid = (np.array(fil.start_mm) + np.array(fil.end_mm)) / 2
            if not solid.contains(mid[None, :])[0]:
                raise ValueError(f"filament {i + 1}'s midpoint lies outside the cavity")
        return self

    def filament_array(self) -> FloatArray:
        """Filaments as rows of (start xyz, end xyz, radius), mm."""
        rows = [[*f.start_mm, *f.end_mm, f.radius_mm] for f in self.filaments]
        return np.array(rows, dtype=np.float64).reshape(-1, 7)

    @property
    def label(self) -> str:
        return self.preset if self.preset is not None else "drawn"

    def build(self) -> Solid:
        if self.preset is not None:
            return make_solid(self.preset, self.size_mm, self.yaw_deg, self.pitch_deg)
        assert self.outline is not None
        assert self.host is not None
        cavity = drawn_cavity(np.array(self.outline), self.host, self.size_mm, smooth=self.smooth)
        solid = extruded_outline(cavity.vertices, self.host, self.depth_fraction * self.size_mm)
        if self.yaw_deg == 0 and self.pitch_deg == 0:
            return solid
        return Rotated(inner=solid, rotation=rotation(self.yaw_deg, self.pitch_deg))


class GravityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tilt_deg: float = Field(default=0.0, ge=0, le=180, description="Tilt from straight down.")
    azimuth_deg: float = Field(
        default=0.0, ge=-360, le=360, description="Direction of the tilt, from +x anticlockwise."
    )

    def vector(self) -> FloatArray:
        return gravity_vector(self.tilt_deg, self.azimuth_deg)


class SliceConfig(BaseModel):
    """A planar cut, given by its normal and its offset from the cavity's centre.
    The default is a vertical cut seen from the front: x to the right, up is up."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tilt_deg: float = Field(
        default=90.0, ge=0, le=180, description="Tilt of the cut's normal from vertical."
    )
    azimuth_deg: float = Field(
        default=270.0, ge=-360, le=360, description="Direction of the normal, from +x."
    )
    offset_mm: float = Field(default=0.0, description="Offset along the normal from the centre.")
    resolution: int = Field(
        default=768, ge=32, le=4096, description="Pixels along its longer side."
    )


class VolumeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    seed: int = Field(0, ge=0)
    archetype: str | None = Field(None, description="Archetype whose criteria judge the slice.")
    grid: VolumeGridConfig = Field(default_factory=VolumeGridConfig)
    solid: SolidConfig
    gravity: GravityConfig = Field(default_factory=GravityConfig)
    model: VolumeModelConfig
    slice: SliceConfig = Field(default_factory=SliceConfig)

    @field_validator("archetype")
    @classmethod
    def _known_archetype(cls, v: str | None) -> str | None:
        if v is not None:
            load_registry().get(v)
        return v

    @model_validator(mode="after")
    def _three_d(self) -> VolumeConfig:
        model = self.model
        if getattr(model, "gravity_deg", DEFAULT_GRAVITY_DEG) != DEFAULT_GRAVITY_DEG:
            raise ValueError(
                "in 3D, gravity is set by `gravity.tilt_deg` and `gravity.azimuth_deg`"
            )
        if isinstance(model, Staged) and model.floor.gravity_deg != DEFAULT_GRAVITY_DEG:
            raise ValueError(
                "in 3D, gravity is set by `gravity.tilt_deg` and `gravity.azimuth_deg`"
            )
        if isinstance(model, Staged) and model.wall_mechanism != "front-feedback":
            raise ValueError("in 3D, staged wall bands use front feedback (H1) only")
        if isinstance(model, Staged) and "dendrite" in model.order:
            raise ValueError("dendrite stages aren't available in the 3D staged model yet")
        if isinstance(model, ProceduralFortification) and model.corner_rounding_mm > 0:
            raise ValueError("corner rounding isn't available in 3D")
        if self.solid.filaments and not isinstance(model, ProceduralGrowth):
            raise ValueError("filaments (tubes) need the growth model, which grows around them")
        if isinstance(model, ProceduralGrowth):
            problem = unsupported_in_3d(model)
            if problem is not None:
                raise ValueError(problem)
        return self

    def with_resolution(self, resolution: int) -> VolumeConfig:
        return self.model_copy(
            update={"grid": self.grid.model_copy(update={"resolution": resolution})}
        )

    def with_slice(self, slice_config: SliceConfig) -> VolumeConfig:
        return self.model_copy(update={"slice": slice_config})

    def to_toml(self) -> str:
        return tomli_w.dumps(self.model_dump(mode="json", exclude_none=True))

    def digest(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def model_digest(self) -> str:
        """Hash of what the formation depends on: everything but the grid and slice."""
        data = self.model_dump(mode="json", exclude={"grid", "slice", "name", "archetype"})
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def parse_volume_config(text: str) -> VolumeConfig:
    return VolumeConfig.model_validate(tomllib.loads(text))


def load_volume_config(path: Path) -> VolumeConfig:
    return parse_volume_config(path.read_text("utf-8"))


def volume_preset_names() -> list[str]:
    files = resources.files("agatesim.volume.presets").iterdir()
    return sorted(f.name.removesuffix(".toml") for f in files if f.name.endswith(".toml"))


def load_volume_preset(name: str) -> VolumeConfig:
    if name not in volume_preset_names():
        raise KeyError(f"unknown 3D preset {name!r}; choose from {volume_preset_names()}")
    text = resources.files("agatesim.volume.presets").joinpath(f"{name}.toml").read_text()
    return parse_volume_config(text)
