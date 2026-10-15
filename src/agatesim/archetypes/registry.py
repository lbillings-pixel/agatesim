"""Load and validate the archetype registry (registry.toml).

Each archetype is a rung on a ladder. A rung may only depend on earlier rungs,
and it counts as verified only when every one of its quantitative criteria
passes against a simulation run (see docs/adr/0004-archetype-ladder.md).
"""

from __future__ import annotations

import tomllib
from enum import StrEnum
from functools import cache
from importlib import resources
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*$")]

SCHEMA_VERSION = 1


class Status(StrEnum):
    PENDING = "pending"  # catalogued; no implementation yet
    IN_PROGRESS = "in-progress"  # implementation underway; criteria not yet all passing
    VERIFIED = "verified"  # every criterion passes in CI


class Subsystem(StrEnum):
    FORMATION = "formation"  # how the agate grows
    OPTICS = "optics"  # how the finished agate looks


class Host(StrEnum):
    VOLCANIC = "volcanic"
    SEDIMENTARY = "sedimentary"
    SEAM = "seam"


class Criterion(BaseModel):
    """One quantitative test an archetype must pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Slug
    description: str
    metric: str  # tentative measurement; refined when the archetype is implemented


class Archetype(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Slug
    name: str
    rung: int = Field(ge=1)
    status: Status
    subsystem: Subsystem
    hosts: tuple[Host, ...] = Field(min_length=1)
    depends_on: tuple[Slug, ...] = ()
    summary: str
    criteria: tuple[Criterion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_criteria(self) -> Archetype:
        ids = [c.id for c in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError(f"archetype {self.id!r} has duplicate criterion ids")
        return self


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    archetypes: tuple[Archetype, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_ladder(self) -> Registry:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"registry schema_version {self.schema_version} != supported {SCHEMA_VERSION}"
            )
        by_id: dict[str, Archetype] = {}
        for a in self.archetypes:
            if a.id in by_id:
                raise ValueError(f"duplicate archetype id {a.id!r}")
            by_id[a.id] = a
        for a in self.archetypes:
            for dep_id in a.depends_on:
                dep = by_id.get(dep_id)
                if dep is None:
                    raise ValueError(f"{a.id!r} depends on unknown archetype {dep_id!r}")
                # Strictly earlier rungs also rules out dependency cycles.
                if dep.rung >= a.rung:
                    raise ValueError(
                        f"{a.id!r} (rung {a.rung}) depends on {dep_id!r} (rung {dep.rung}); "
                        "dependencies must sit on earlier rungs"
                    )
                if a.status is Status.VERIFIED and dep.status is not Status.VERIFIED:
                    raise ValueError(f"{a.id!r} is verified but its dependency {dep_id!r} is not")
        return self

    def get(self, archetype_id: str) -> Archetype:
        for a in self.archetypes:
            if a.id == archetype_id:
                return a
        raise KeyError(archetype_id)

    def by_rung(self) -> list[Archetype]:
        return sorted(self.archetypes, key=lambda a: (a.rung, a.id))


def parse_registry(text: str) -> Registry:
    return Registry.model_validate(tomllib.loads(text))


@cache
def load_registry() -> Registry:
    """Load the registry shipped with the package."""
    text = resources.files("agatesim.archetypes").joinpath("registry.toml").read_text("utf-8")
    return parse_registry(text)


def to_markdown(registry: Registry) -> str:
    """Render the registry as docs/archetypes.md. CI checks the file stays in sync."""
    lines = [
        "# Archetype ladder",
        "",
        "<!-- Generated from src/agatesim/archetypes/registry.toml by",
        "     `agatesim archetypes --write docs/archetypes.md`. Do not edit by hand. -->",
        "",
        "Each archetype is an agate form the simulator aims to reproduce. An archetype is",
        "**verified** only when every criterion below passes against a simulation run.",
        "Metrics are provisional until the archetype is implemented.",
        "",
        "| Rung | Archetype | Status | Subsystem | Hosts | Depends on |",
        "|---:|---|---|---|---|---|",
    ]
    for a in registry.by_rung():
        deps = ", ".join(a.depends_on) or "—"
        hosts = ", ".join(h.value for h in a.hosts)
        lines.append(
            f"| {a.rung} | [{a.name}](#{a.id}) | {a.status.value} | {a.subsystem.value} "
            f"| {hosts} | {deps} |"
        )
    for a in registry.by_rung():
        lines += ["", f"## {a.name}", "", f'<a id="{a.id}"></a>', "", a.summary.strip(), ""]
        lines += ["| Criterion | Description | Provisional metric |", "|---|---|---|"]
        lines += [f"| `{c.id}` | {c.description} | {c.metric} |" for c in a.criteria]
    return "\n".join(lines) + "\n"
