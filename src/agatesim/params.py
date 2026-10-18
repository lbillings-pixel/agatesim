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
    explore: tuple[float, float] | None = None,
    log: bool = False,
    key: bool = False,
) -> Any:
    """A pydantic Field annotated with units and nature in its JSON schema (plus
    any `schema_extra`, such as a used_when hint).

    `explore` is the bounded range the app's Randomize draws from (on a log scale
    with `log`): values that keep the model in its working regime, inside the
    setting's limits. A setting with a range, or with `key`, is one of the model's
    key settings, which the app shows first."""
    extra: dict[str, Any] = {"units": units, "nature": nature.value, **(schema_extra or {})}
    if explore is not None:
        lo, hi = explore
        if not lo < hi:
            raise ValueError(f"explore range must be increasing, got {explore}")
        if log and lo <= 0:
            raise ValueError(f"a log explore range must be positive, got {explore}")
        extra["explore"] = {"min": lo, "max": hi, "log": log}
    if key or explore is not None:
        extra["key"] = True
    return Field(
        default, description=description, ge=ge, gt=gt, le=le, lt=lt, json_schema_extra=extra
    )


KEY: dict[str, Any] = {"key": True}  # schema extra marking a choice or switch as a key setting


def used_when(*alternatives: dict[str, list[str]]) -> dict[str, Any]:
    """Schema hint for the app: a setting matters only when, for one of the
    alternatives, every named sibling's value is one of the listed values (on/off
    settings as "true" or "false") or is a stage order containing one of them
    as a stage."""
    return {"used_when": list(alternatives)}
