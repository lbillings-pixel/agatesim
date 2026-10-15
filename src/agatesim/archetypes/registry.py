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

SCHEMA_VERSION = 2


class Status(StrEnum):
    PENDING = "pending"  # catalogued; no implementation yet
    IN_PROGRESS = "in-progress"  # implementation underway; criteria not yet all passing
    VERIFIED = "verified"  # a committed preset passes every criterion in CI


class Tier(StrEnum):
    """Model tiers are verified separately (ADR 0005): reproducing a form
    procedurally says nothing about which mechanism forms it."""

    PROCEDURAL = "procedural"
    MECHANISTIC = "mechanistic"


class TierStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    procedural: Status = Status.PENDING
    mechanistic: Status = Status.PENDING

    def of(self, tier: Tier) -> Status:
        return Status(getattr(self, tier.value))


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
    metric: str  # what is measured; provisional until the archetype is implemented
    min: float | None = None  # pass if value >= min
    max: float | None = None  # pass if value <= max

    @model_validator(mode="after")
    def _ordered_bounds(self) -> Criterion:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"criterion {self.id!r} has min > max")
        return self

    def pass_condition(self) -> str:
        if self.min is not None and self.max is not None:
            return f"{self.min:g} ≤ value ≤ {self.max:g}"
        if self.min is not None:
            return f"value ≥ {self.min:g}"
        if self.max is not None:
            return f"value ≤ {self.max:g}"
        return "provisional"


class Archetype(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Slug
    name: str
    rung: int = Field(ge=1)
    status: TierStatus
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
                for tier in Tier:
                    if (
                        a.status.of(tier) is Status.VERIFIED
                        and dep.status.of(tier) is not Status.VERIFIED
                    ):
                        raise ValueError(
                            f"{a.id!r} is verified ({tier.value}) but its dependency "
                            f"{dep_id!r} is not"
                        )
            for c in a.criteria:
                verified = any(a.status.of(t) is Status.VERIFIED for t in Tier)
                if verified and c.min is None and c.max is None:
                    raise ValueError(
                        f"{a.id!r} is verified but criterion {c.id!r} has no threshold"
                    )
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
        "**verified** for a model tier only when a committed preset using that tier passes",
        "every criterion below in CI (ADR 0005). Criteria without a threshold are",
        "provisional until the archetype is implemented.",
        "",
        "| Rung | Archetype | Procedural | Mechanistic | Subsystem | Hosts | Depends on |",
        "|---:|---|---|---|---|---|---|",
    ]
    for a in registry.by_rung():
        deps = ", ".join(a.depends_on) or "—"
        hosts = ", ".join(h.value for h in a.hosts)
        lines.append(
            f"| {a.rung} | [{a.name}](#{a.id}) | {a.status.procedural.value} "
            f"| {a.status.mechanistic.value} | {a.subsystem.value} | {hosts} | {deps} |"
        )
    for a in registry.by_rung():
        lines += ["", f"## {a.name}", "", f'<a id="{a.id}"></a>', "", a.summary.strip(), ""]
        lines += ["| Criterion | Description | Metric | Pass if |", "|---|---|---|---|"]
        lines += [
            f"| `{c.id}` | {c.description} | {c.metric} | {c.pass_condition()} |"
            for c in a.criteria
        ]
    return "\n".join(lines) + "\n"
