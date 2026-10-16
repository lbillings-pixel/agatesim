"""Formation stages on the deposition-time axis (for the growth animation)."""

import itertools

from agatesim.config import load_preset
from agatesim.stages import formation_stages


def test_growth_stages_follow_the_schedules() -> None:
    stages = formation_stages(load_preset("quartz-geode").model)
    assert [s.label for s in stages] == ["wall lining", "quartz crystals"]
    assert stages[0].start == 0.0
    assert stages[-1].end == 1.0
    assert abs(stages[0].end - 0.35) < 1e-9


def test_staged_model_stages_take_equal_slots() -> None:
    stages = formation_stages(load_preset("fortification-waterline-mechanistic").model)
    assert [s.label for s in stages] == [
        "wall lining (H1)",
        "floor layers (H4)",
        "wall lining (H1)",
    ]
    assert [round(s.end, 3) for s in stages] == [0.333, 0.667, 1.0]


def test_stages_cover_the_axis_without_gaps() -> None:
    for name in ["eye", "moss", "fortification-waterline", "waterline-mechanistic"]:
        stages = formation_stages(load_preset(name).model)
        assert stages[0].start == 0.0
        assert stages[-1].end == 1.0
        assert all(a.end == b.start for a, b in itertools.pairwise(stages))
