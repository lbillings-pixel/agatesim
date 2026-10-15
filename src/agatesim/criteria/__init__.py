"""Archetype criteria: measure a result and judge it against the registry's thresholds.

Thresholds live in the registry (the contract); measurements live here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agatesim.archetypes import load_registry
from agatesim.criteria import combined, fortification, quartz_geode, seam, waterline
from agatesim.criteria.types import Measurement
from agatesim.simulate import SimulationResult

EVALUATORS: dict[str, Callable[[SimulationResult], dict[str, Measurement]]] = {
    "fortification": fortification.evaluate,
    "seam": seam.evaluate,
    "waterline": waterline.evaluate,
    "fortification-waterline": combined.evaluate,
    "quartz-geode": quartz_geode.evaluate,
}


@dataclass(frozen=True)
class CriterionResult:
    id: str
    value: float | None
    min: float | None
    max: float | None
    passed: bool
    detail: str


@dataclass(frozen=True)
class Evaluation:
    archetype: str
    results: tuple[CriterionResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def to_json(self) -> dict[str, object]:
        return {
            "archetype": self.archetype,
            "passed": self.passed,
            "criteria": [r.__dict__ for r in self.results],
        }


def implemented() -> set[str]:
    return set(EVALUATORS)


def evaluate(archetype_id: str, result: SimulationResult) -> Evaluation:
    archetype = load_registry().get(archetype_id)
    if archetype_id not in EVALUATORS:
        raise NotImplementedError(f"no criteria implemented yet for {archetype_id!r}")
    measured = EVALUATORS[archetype_id](result)
    expected = {c.id for c in archetype.criteria}
    if set(measured) != expected:
        raise RuntimeError(
            f"{archetype_id}: measured {sorted(measured)} != registry {sorted(expected)}"
        )
    results: list[CriterionResult] = []
    for c in archetype.criteria:
        raw, detail = measured[c.id]
        value = None if raw is None else float(raw)
        passed = bool(
            value is not None
            and (c.min is None or value >= c.min)
            and (c.max is None or value <= c.max)
        )
        results.append(
            CriterionResult(
                id=c.id, value=value, min=c.min, max=c.max, passed=passed, detail=detail
            )
        )
    return Evaluation(archetype=archetype_id, results=tuple(results))
