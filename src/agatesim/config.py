"""Run configuration: everything needed to reproduce a run, read from TOML."""

from __future__ import annotations

import hashlib
import json
import tomllib
from importlib import resources
from pathlib import Path
from typing import Annotated

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from agatesim.archetypes import load_registry
from agatesim.geometry import CAVITY_PRESETS
from agatesim.models import ProceduralFortification, ProceduralWaterline

ModelConfig = Annotated[ProceduralFortification | ProceduralWaterline, Field(discriminator="kind")]


class GridConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resolution: int = Field(
        default=768, ge=32, le=8192, description="Pixels along the longer side."
    )
    margin_fraction: float = Field(
        default=0.08, ge=0, le=0.5, description="Host-rock border width."
    )


class CavityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    preset: str
    size_mm: float = Field(50.0, gt=0, description="Longest dimension of the cavity.")
    rotation_deg: float = 0.0

    @field_validator("preset")
    @classmethod
    def _known_preset(cls, v: str) -> str:
        if v not in CAVITY_PRESETS:
            raise ValueError(f"unknown cavity preset {v!r}; choose from {sorted(CAVITY_PRESETS)}")
        return v


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    seed: int = Field(0, ge=0)
    archetype: str | None = Field(None, description="Archetype whose criteria judge this run.")
    grid: GridConfig = Field(default_factory=GridConfig)
    cavity: CavityConfig
    model: ModelConfig

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


def load_preset(name: str) -> RunConfig:
    if name not in preset_names():
        raise KeyError(f"unknown preset {name!r}; choose from {preset_names()}")
    return parse_config(resources.files("agatesim.presets").joinpath(f"{name}.toml").read_text())
