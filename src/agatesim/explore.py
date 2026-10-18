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
from typing import Any, Literal, cast, get_args

import numpy as np
from pydantic import BaseModel

from agatesim.config import RunConfig
from agatesim.criteria import evaluate
from agatesim.fields import Phase
from agatesim.geometry import CAVITY_PRESETS
from agatesim.models.staged import Order, Staged
from agatesim.simulate import simulate

CHECK_RESOLUTION = 192  # pixels across the quick run that checks a mechanistic draw
FORM_RESOLUTION = 768  # most pixels across the run that checks the form, when asked
MIN_BANDS = 4  # a mechanistic draw must still lay at least this many bands
MAX_ATTEMPTS = 12
UNCHECKED = {"mechanistic-liesegang"}  # needs the GPU; it has no ranges either
SIZE_SPAN = math.log(1.3)  # cavity size varies by up to this factor either way
TIME_SHIFT = 0.1  # schedule events move by up to this share of the run
CONTINUOUS = {"silica", "iron"}  # schedules whose levels vary (the rest are on/off switches)

Extra = Literal["cavity", "schedules", "order"]


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


def _vary_cavity(config: RunConfig, strength: float, rng: np.random.Generator) -> RunConfig:
    """Another preset shape of the same host (with probability `strength`), a
    size within a factor of 1.3 either way, any rotation. Left alone when tubes
    are placed: they might not fit a new shape."""
    cavity = config.cavity
    if cavity.tubes:
        return config
    preset = cavity.preset
    if preset is not None and rng.random() < strength:
        host = CAVITY_PRESETS[preset].host
        same = sorted(name for name, p in CAVITY_PRESETS.items() if p.host is host)
        preset = same[int(rng.integers(0, len(same)))]
    size = cavity.size_mm * math.exp(strength * rng.uniform(-SIZE_SPAN, SIZE_SPAN))
    rotation = (cavity.rotation_deg + strength * rng.uniform(-180.0, 180.0)) % 360.0
    new = cavity.model_copy(
        update={"preset": preset, "size_mm": min(max(size, 10.0), 150.0), "rotation_deg": rotation}
    )
    return config.model_copy(update={"cavity": new})


def _vary_schedules(values: dict[str, Any], strength: float, rng: np.random.Generator) -> None:
    """Shift each schedule's events in time, and vary the levels of the
    continuous ones (silica, iron) within 0-1. On/off switches keep their values,
    so no stage is switched on or off by accident."""
    schedules = values.get("schedules")
    if not isinstance(schedules, dict):
        return

    def shift(x: float) -> float:
        return min(max(float(x) + strength * rng.uniform(-TIME_SHIFT, TIME_SHIFT), 0.0), 1.0)

    def level(v: float) -> float:
        return float(v) + 0.5 * strength * (rng.uniform(0.0, 1.0) - float(v))

    for key, schedule in cast(dict[str, dict[str, Any]], schedules).items():
        if key in CONTINUOUS:
            schedule["base"] = level(schedule["base"])
        for event in cast(list[dict[str, Any]], schedule.get("events", [])):
            if event["type"] == "ramp":
                a, b = sorted((shift(event["start"]), shift(event["end"])))
                event["start"], event["end"] = a, min(max(b, a + 0.01), 1.0)
            elif event["type"] == "pulse":
                event["at"] = min(shift(event["at"]), 1.0 - float(event["width"]))
            else:
                event["at"] = shift(event["at"])
            if key in CONTINUOUS:
                event["value"] = level(event["value"])


def vary(
    config: RunConfig,
    strength: float,
    rng: np.random.Generator,
    extras: frozenset[Extra] = frozenset(),
) -> RunConfig:
    """One draw: the key settings moved toward random values in their ranges, a
    new seed, and any `extras` (cavity, schedules, stage order) varied too."""
    model = config.model
    schema = type(model).model_json_schema()
    values = _vary(model.model_dump(mode="json"), schema["properties"], schema, strength, rng)
    if "schedules" in extras:
        _vary_schedules(values, strength, rng)
    if "order" in extras and isinstance(model, Staged) and rng.random() < strength:
        orders = get_args(Order)
        values["order"] = orders[int(rng.integers(0, len(orders)))]
    new_model = cast(BaseModel, type(model).model_validate(values))
    drawn = config.model_copy(update={"model": new_model, "seed": int(rng.integers(0, 1_000_000))})
    if "cavity" in extras:
        drawn = _vary_cavity(drawn, strength, rng)
    return drawn


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
    config: RunConfig,
    strength: float,
    *,
    keep_form: bool = False,
    seed: int | None = None,
    extras: frozenset[Extra] = frozenset(),
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
        return Draw(vary(config, strength, rng, extras), 1, False, True, "")
    last = config
    reason = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        last = vary(config, strength, rng, extras)
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
