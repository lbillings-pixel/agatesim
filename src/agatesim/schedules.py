"""Schedules: environmental conditions that change over formation time.

Formation time τ runs from 0 (the empty cavity) to 1 (the end of the run). A
schedule is a base value plus events:

- **step**: from `at` onward, the value becomes `value`;
- **ramp**: from `start` to `end`, the value moves linearly from whatever it was
  at `start` to `value`, then holds there;
- **pulse**: during [`at`, `at` + `width`), the value is `value`; afterwards it
  returns to what the steps and ramps say.

Steps and ramps apply in order of their start times, each starting from the value
the schedule had at that moment. Pulses are laid over the result. The web UI
mirrors these rules (web/src/lib/schedule.ts); tests/fixtures/schedules.json pins
both implementations to the same numbers.
"""

from __future__ import annotations

from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agatesim.grid import FloatArray

Time = Annotated[float, Field(ge=0.0, le=1.0)]
EPS = 1e-9


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["step"] = "step"
    at: Time
    value: float

    @property
    def start(self) -> float:
        return self.at


class Ramp(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["ramp"] = "ramp"
    start: Time
    end: Time
    value: float

    @model_validator(mode="after")
    def _ordered(self) -> Ramp:
        if self.end <= self.start:
            raise ValueError("a ramp must end after it starts")
        return self


class Pulse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["pulse"] = "pulse"
    at: Time
    width: float = Field(gt=0.0, le=1.0)
    value: float


Event = Annotated[Step | Ramp | Pulse, Field(discriminator="type")]


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base: float
    events: tuple[Event, ...] = ()

    def values(self) -> list[float]:
        return [self.base, *(e.value for e in self.events)]

    def sample(self, t: FloatArray) -> FloatArray:
        t = np.asarray(t, dtype=np.float64)
        background = [e for e in self.events if not isinstance(e, Pulse)]
        out = _apply(self.base, sorted(background, key=_start), t)
        for e in self.events:
            if isinstance(e, Pulse):
                # EPS keeps the pulse end exclusive despite rounding (0.4 + 0.2 > 0.6).
                out[(t >= e.at) & (t < e.at + e.width - EPS)] = e.value
        return out


def _start(e: Step | Ramp) -> float:
    return e.at if isinstance(e, Step) else e.start


def _apply(base: float, events: list[Step | Ramp], t: FloatArray) -> FloatArray:
    out = np.full(t.shape, base, dtype=np.float64)
    for i, e in enumerate(events):
        if isinstance(e, Step):
            out[t >= e.at] = e.value
        else:
            # The ramp starts from the value the earlier events give at its start.
            v0 = float(_apply(base, events[:i], np.array([e.start]))[0])
            inside = (t >= e.start) & (t < e.end)
            out[inside] = v0 + (e.value - v0) * (t[inside] - e.start) / (e.end - e.start)
            out[t >= e.end] = e.value
    return out
