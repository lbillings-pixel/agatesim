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
) -> Any:
    """A pydantic Field annotated with units and nature in its JSON schema."""
    return Field(
        default,
        description=description,
        ge=ge,
        gt=gt,
        le=le,
        lt=lt,
        json_schema_extra={"units": units, "nature": nature.value},
    )
