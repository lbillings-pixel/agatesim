import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from agatesim.schedules import Schedule

T = np.array([0.0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0])


def _s(base: float, *events: dict[str, object]) -> Schedule:
    return Schedule.model_validate({"base": base, "events": list(events)})


def test_constant() -> None:
    np.testing.assert_array_equal(_s(0.3).sample(T), np.full(T.shape, 0.3))


def test_step() -> None:
    out = _s(1.0, {"type": "step", "at": 0.5, "value": 0.2}).sample(T)
    np.testing.assert_allclose(out, [1, 1, 1, 1, 0.2, 0.2, 0.2, 0.2, 0.2])


def test_ramp_starts_from_current_value_and_holds() -> None:
    out = _s(
        0.0,
        {"type": "step", "at": 0.1, "value": 0.4},
        {"type": "ramp", "start": 0.4, "end": 0.6, "value": 1.0},
    ).sample(T)
    np.testing.assert_allclose(out, [0, 0.4, 0.4, 0.4, 0.7, 1, 1, 1, 1])


def test_pulse_overlays_and_returns() -> None:
    out = _s(0.2, {"type": "pulse", "at": 0.4, "width": 0.2, "value": 1.0}).sample(T)
    np.testing.assert_allclose(out, [0.2, 0.2, 0.2, 1, 1, 0.2, 0.2, 0.2, 0.2])


def test_event_order_in_list_does_not_matter_for_steps() -> None:
    a = _s(1, {"type": "step", "at": 0.6, "value": 0.1}, {"type": "step", "at": 0.2, "value": 0.5})
    b = _s(1, {"type": "step", "at": 0.2, "value": 0.5}, {"type": "step", "at": 0.6, "value": 0.1})
    np.testing.assert_array_equal(a.sample(T), b.sample(T))


@pytest.mark.parametrize(
    "event",
    [
        {"type": "ramp", "start": 0.6, "end": 0.4, "value": 1},
        {"type": "pulse", "at": 0.5, "width": 0, "value": 1},
        {"type": "step", "at": 1.5, "value": 1},
        {"type": "wiggle", "at": 0.5, "value": 1},
    ],
)
def test_invalid_events_rejected(event: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _s(0, event)


def test_python_matches_shared_fixture(repo_root: Path) -> None:
    """The web UI's schedule plot uses the same fixture (web/src/lib/schedule.test.ts)."""
    cases = json.loads((repo_root / "tests" / "fixtures" / "schedules.json").read_text("utf-8"))
    for case in cases:
        got = Schedule.model_validate(case["schedule"]).sample(np.array(case["t"]))
        np.testing.assert_allclose(got, case["expected"], atol=1e-12, err_msg=case["name"])
