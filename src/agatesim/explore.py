"""Randomize a run's settings within bounded ranges, to explore its variety.

Each key setting with an `explore` range (agatesim.params) moves toward a value
drawn from that range: all the way at strength 1, part of the way below it, on
a log scale where the range says so. Draws stay inside the range's span and the
setting's own limits, so nothing runs away. Settings without a range (the
cavity, the schedules, choices) are kept.

Mechanistic models can stop working away from their regime (H1's rhythm needs
its feedback in a narrow window), so each mechanistic draw is checked with a
quick small run and redrawn if it no longer bands, or, if asked, no longer
passes the form it is judged as.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from pydantic import BaseModel

from agatesim.config import RunConfig
from agatesim.criteria import evaluate
from agatesim.fields import Phase
from agatesim.simulate import simulate

CHECK_RESOLUTION = 192  # pixels across the quick run that checks a mechanistic draw
FORM_RESOLUTION = 768  # most pixels across the run that checks the form, when asked
MIN_BANDS = 4  # a mechanistic draw must still lay at least this many bands
MAX_ATTEMPTS = 12
UNCHECKED = {"mechanistic-liesegang"}  # needs the GPU; it has no ranges either


@dataclass(frozen=True)
class Draw:
    config: RunConfig
    attempts: int
    checked: bool  # a quick run vetted the draw
    accepted: bool  # it passed the checks (always True when unchecked)
    note: str


def _resolve(schema: dict[str, Any], prop: dict[str, Any]) -> dict[str, Any] | None:
    ref = prop.get("$ref")
    if ref is None and prop.get("allOf"):
        ref = prop["allOf"][0].get("$ref")
    if not isinstance(ref, str):
        return None
    return cast(dict[str, Any], schema["$defs"][ref.split("/")[-1]])


def _bounds(prop: dict[str, Any]) -> tuple[float, float]:
    lo = prop.get("minimum", prop.get("exclusiveMinimum", -math.inf))
    hi = prop.get("maximum", prop.get("exclusiveMaximum", math.inf))
    return float(lo), float(hi)


def _vary(
    values: dict[str, Any],
    props: dict[str, Any],
    schema: dict[str, Any],
    strength: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    out = dict(values)
    for key, prop in props.items():
        nested = _resolve(schema, prop)
        if nested is not None:
            inner = out.get(key)
            if isinstance(inner, dict):
                out[key] = _vary(
                    cast(dict[str, Any], inner), nested["properties"], schema, strength, rng
                )
            continue
        explore = prop.get("explore")
        current = out.get(key)
        if not isinstance(explore, dict) or not isinstance(current, int | float):
            continue
        spec = cast(dict[str, Any], explore)
        lo, hi, log = float(spec["min"]), float(spec["max"]), bool(spec["log"])
        if log:
            target = math.exp(rng.uniform(math.log(lo), math.log(hi)))
            now = max(float(current), lo * 1e-3)
            value = math.exp(math.log(now) + strength * (math.log(target) - math.log(now)))
        else:
            target = rng.uniform(lo, hi)
            value = float(current) + strength * (target - float(current))
        # Stay within the range's span (or the current value, if that lies outside)
        # and the setting's own limits.
        value = min(max(value, min(lo, float(current))), max(hi, float(current)))
        floor, ceiling = _bounds(prop)
        value = min(max(value, floor), ceiling)
        out[key] = round(value) if prop.get("type") == "integer" else value
    return out


def vary(config: RunConfig, strength: float, rng: np.random.Generator) -> RunConfig:
    """One draw: the key settings moved toward random values in their ranges,
    and a new seed."""
    model = config.model
    schema = type(model).model_json_schema()
    values = _vary(model.model_dump(mode="json"), schema["properties"], schema, strength, rng)
    new_model = cast(BaseModel, type(model).model_validate(values))
    return config.model_copy(update={"model": new_model, "seed": int(rng.integers(0, 1_000_000))})


def _vet(config: RunConfig, keep_form: bool) -> str | None:
    """Why a mechanistic draw fails, or None if it is fine."""
    result = simulate(config.with_resolution(CHECK_RESOLUTION))
    f = result.fields
    agate = (f.phase == Phase.CHALCEDONY) & (f.band >= 0)
    bands = len(np.unique(f.band[agate]))
    if bands < MIN_BANDS:
        return f"only {bands} bands"
    if keep_form and config.archetype:
        # The form's tests need the resolution its presets are verified at (corners, say).
        resolution = min(config.grid.resolution, FORM_RESOLUTION)
        ev = evaluate(config.archetype, simulate(config.with_resolution(resolution)))
        if not ev.passed:
            return "no longer passes " + ", ".join(r.id for r in ev.results if not r.passed)
    return None


def randomize(
    config: RunConfig, strength: float, *, keep_form: bool = False, seed: int | None = None
) -> Draw:
    """Draw new settings. For mechanistic models, or any model with keep_form and
    a form to judge, redraw until a quick run still bands (and still passes the
    judged form, with keep_form), up to MAX_ATTEMPTS."""
    rng = np.random.default_rng(seed)
    strength = min(max(strength, 0.0), 1.0)
    kind = config.model.kind
    mechanistic = kind.startswith("mechanistic-") and kind not in UNCHECKED
    form = keep_form and config.archetype is not None and kind not in UNCHECKED
    if not (mechanistic or form):
        return Draw(vary(config, strength, rng), 1, False, True, "")
    last = config
    reason = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        last = vary(config, strength, rng)
        problem = _vet(last, keep_form)
        if problem is None:
            return Draw(last, attempt, True, True, "")
        reason = problem
    return Draw(
        config,
        MAX_ATTEMPTS,
        True,
        False,
        f"no draw in {MAX_ATTEMPTS} tries kept working ({reason}); settings left unchanged",
    )
