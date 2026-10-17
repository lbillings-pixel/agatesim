"""Model parameter declarations.

Every model parameter carries units and a *nature* (ADR 0003, refined in ADR 0005),
which the UI displays so nobody mistakes a model knob for a measured condition.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field


class Nature(StrEnum):
    PHYSICAL = "physical"  # an environmental condition with units, e.g. the gravity direction
    EFFECTIVE = "effective"  # a model coefficient with no direct measurement
    IMPOSED = "imposed"  # a property of the result set directly (procedural models only)


def param(
    default: float,
    *,
    units: str,
    nature: Nature,
    description: str,
    ge: float | None = None,
    gt: float | None = None,
    le: float | None = None,
    lt: float | None = None,
    schema_extra: dict[str, Any] | None = None,
) -> Any:
    """A pydantic Field annotated with units and nature in its JSON schema (plus
    any `schema_extra`, such as a used_when hint)."""
    return Field(
        default,
        description=description,
        ge=ge,
        gt=gt,
        le=le,
        lt=lt,
        json_schema_extra={"units": units, "nature": nature.value, **(schema_extra or {})},
    )


def used_when(*alternatives: dict[str, list[str]]) -> dict[str, Any]:
    """Schema hint for the app: a setting matters only when, for one of the
    alternatives, every named sibling's value is one of the listed values (on/off
    settings as "true" or "false") or is a stage order containing one of them
    as a stage."""
    return {"used_when": list(alternatives)}
