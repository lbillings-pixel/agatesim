"""Run configuration: everything needed to reproduce a run, read from TOML."""

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
from agatesim.geometry import (
    CAVITY_PRESETS,
    MAX_OUTLINE_POINTS,
    MIN_OUTLINE_POINTS,
    Cavity,
    drawn_cavity,
    make_cavity,
)
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

ModelConfig = Annotated[
    ProceduralFortification
    | ProceduralWaterline
    | ProceduralGrowth
    | FrontFeedback
    | Liesegang
    | Settling
    | Staged,
    Field(discriminator="kind"),
]


class GridConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resolution: int = Field(
        default=768, ge=32, le=8192, description="Pixels along the longer side."
    )
    margin_fraction: float = Field(
        default=0.08, ge=0, le=0.5, description="Host-rock border width."
    )


class TubeConfig(BaseModel):
    """A thin filament crossing the slab (a tube agate seed), seen end-on."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x_mm: float = Field(description="Position in the slab, mm from the cavity centre.")
    y_mm: float = Field(description="Position in the slab, mm from the cavity centre (up).")
    radius_mm: float = Field(default=0.3, gt=0, le=10, description="Filament radius.")


class CavityConfig(BaseModel):
    """A preset shape, or a drawn outline with its host setting. Exactly one of
    `preset` and `outline` is given."""

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
    smooth: bool = Field(
        default=False, description="Smooth a drawn outline instead of keeping its corners."
    )
    size_mm: float = Field(default=50.0, gt=0, description="Longest dimension of the cavity.")
    rotation_deg: float = 0.0
    tubes: list[TubeConfig] = Field(default_factory=list[TubeConfig], max_length=200)

    @field_validator("preset")
    @classmethod
    def _known_preset(cls, v: str | None) -> str | None:
        if v is not None and v not in CAVITY_PRESETS:
            raise ValueError(f"unknown cavity preset {v!r}; choose from {sorted(CAVITY_PRESETS)}")
        return v

    @model_validator(mode="after")
    def _one_shape(self) -> CavityConfig:
        if (self.preset is None) == (self.outline is None):
            raise ValueError("give exactly one of `preset` and `outline`")
        if self.outline is None and (self.host is not None or self.smooth):
            raise ValueError("`host` and `smooth` apply only to a drawn `outline`")
        if self.outline is not None and self.host is None:
            raise ValueError("a drawn `outline` needs a `host` (volcanic, sedimentary or seam)")
        cavity = self.build()  # raises ValueError for a bad outline
        for i, tube in enumerate(self.tubes):
            problem = cavity.tube_problem(np.array([tube.x_mm, tube.y_mm]), tube.radius_mm)
            if problem is not None:
                raise ValueError(f"tube {i + 1} {problem}")
        return self

    @property
    def label(self) -> str:
        return self.preset if self.preset is not None else "drawn"

    def build(self) -> Cavity:
        if self.preset is not None:
            return make_cavity(self.preset, self.size_mm, self.rotation_deg)
        assert self.outline is not None
        assert self.host is not None
        return drawn_cavity(
            np.array(self.outline), self.host, self.size_mm, self.rotation_deg, smooth=self.smooth
        )

    def tube_array(self) -> FloatArray:
        """Tubes as rows of (x, y, radius), mm."""
        return np.array([[t.x_mm, t.y_mm, t.radius_mm] for t in self.tubes]).reshape(-1, 3)


class OpticsConfig(BaseModel):
    """The slab as an optical object (ADR 0010). The formation models describe the
    cut surface; these settings say how the banding continues beneath it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    thickness_mm: float = Field(
        default=3.0, gt=0, le=30, description="Slab thickness, for light passing into it."
    )
    slice_mm: float = Field(
        default=0.3,
        gt=0,
        le=3,
        description=(
            "Thickness of the thin slice the backlit (iris) view looks through: iris "
            "colours show only in thin slices."
        ),
    )
    band_tilt_deg: float = Field(
        default=30.0,
        ge=0,
        lt=85,
        description=(
            "Tilt of the band surfaces from the slab normal beneath the cut "
            "(0 = bands run straight down through the slab)."
        ),
    )


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    seed: int = Field(0, ge=0)
    archetype: str | None = Field(None, description="Archetype whose criteria judge this run.")
    grid: GridConfig = Field(default_factory=GridConfig)
    cavity: CavityConfig
    model: ModelConfig
    optics: OpticsConfig = Field(default_factory=OpticsConfig)

    @field_validator("archetype")
    @classmethod
    def _known_archetype(cls, v: str | None) -> str | None:
        if v is not None:
            load_registry().get(v)  # raises KeyError if unknown
        return v

    def with_resolution(self, resolution: int) -> RunConfig:
        return self.model_copy(
            update={"grid": self.grid.model_copy(update={"resolution": resolution})}
        )

    def to_toml(self) -> str:
        return tomli_w.dumps(self.model_dump(mode="json", exclude_none=True))

    def digest(self) -> str:
        """Stable hash of the full configuration."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


def parse_config(text: str) -> RunConfig:
    return RunConfig.model_validate(tomllib.loads(text))


def load_config(path: Path) -> RunConfig:
    return parse_config(path.read_text("utf-8"))


def preset_names() -> list[str]:
    files = resources.files("agatesim.presets").iterdir()
    return sorted(f.name.removesuffix(".toml") for f in files if f.name.endswith(".toml"))


def preset_description(name: str) -> str:
    """The comment at the top of a preset's file: what it shows and how, in prose."""
    if name not in preset_names():
        raise KeyError(f"unknown preset {name!r}; choose from {preset_names()}")
    text = resources.files("agatesim.presets").joinpath(f"{name}.toml").read_text(encoding="utf-8")
    lines: list[str] = []
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        lines.append(line.removeprefix("#").strip())
    return " ".join(lines)


def load_preset(name: str) -> RunConfig:
    if name not in preset_names():
        raise KeyError(f"unknown preset {name!r}; choose from {preset_names()}")
    return parse_config(resources.files("agatesim.presets").joinpath(f"{name}.toml").read_text())
