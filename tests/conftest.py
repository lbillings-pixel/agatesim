from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agatesim.server.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]

# Tests taking 5 s or more (measured 2026-10-25, refreshed 2026-11-10, full suite
# 17 min): marked `slow`, so `pytest -m "not slow"` is a quick tier of about 8 min.
# CI runs everything. Refresh
# from `pytest --durations=50`; a whole test is named without its [case].
# tests/test_slow_list.py checks every entry still names a test.
SLOW = frozenset(
    {
        "tests/test_materials_along_bands.py::test_lenses_drift_and_channels_keep_to_their_own_streams",
        "tests/test_materials_along_bands.py::test_no_arrival_time_moves",
        "tests/test_specimen.py::test_photo_passes_are_never_false_positives[botryoidal]",
        "tests/test_specimen.py::test_photo_passes_are_never_false_positives[fortification]",
        "tests/test_specimen.py::test_segmentation_finds_the_slab[fortification]",
        "tests/test_specimen.py::test_segmentation_finds_the_slab[waterline]",
        "tests/test_reference_regression.py::test_photo_analysis_of_the_reference_photos_is_unchanged",
        "tests/test_staged.py::test_preview_matches_full_run",
        "tests/test_staged.py::test_floor_layers_are_horizontal_and_wall_bands_follow_the_wall",
        "tests/test_staged.py::test_the_stage_order_follows_the_configuration",
        "tests/test_staged.py::test_the_rim_fills_its_share_and_stages_never_overlap",
        "tests/test_staged.py::test_liesegang_walls_after_a_settled_floor",
        "tests/test_staged.py::test_garden_tubes_rise_from_the_floor_and_ignore_the_grid",
        "tests/test_server.py::test_specimen_workflow",
        "tests/test_server.py::test_every_mechanistic_preset_previews[fortification-waterline-mechanistic]",
        "tests/test_criteria.py::test_verification_preset_passes[shadow]",
        "tests/test_criteria.py::test_mechanistic_verification_preset_passes[shadow]",
        "tests/test_criteria.py::test_mechanistic_verification_preset_passes[fortification-waterline]",
        "tests/test_volume_fronts.py::test_garden_tubes_grow_upward_only_with_buoyancy",
        "tests/test_volume_fronts.py::test_garden_tubes_rise_in_3d_and_h1_encloses_them",
        "tests/test_volume_fronts.py::test_mechanistic_3d_presets_pass_on_their_configured_cut[plume-mechanistic-3d]",
        "tests/test_volume_fronts.py::test_mechanistic_3d_presets_pass_on_their_configured_cut[eye-mechanistic-3d]",
        "tests/test_volume_fronts.py::test_mechanistic_3d_presets_pass_on_their_configured_cut[botryoidal-mechanistic-3d]",
        "tests/test_volume_fronts.py::test_mechanistic_3d_presets_pass_on_their_configured_cut[quartz-geode-mechanistic-3d]",
        "tests/test_volume_fronts.py::test_the_spherulite_stage_fills_its_share_then_lining_fills_the_rest",
        "tests/test_volume_fronts.py::test_3d_geode_crystals_fill_only_the_quartz_and_coarsen_inward",
        "tests/test_volume_growth.py::test_quartz_crystals_coarsen_inward_in_3d",
        "tests/test_volume_growth.py::test_quartz_never_touches_the_wall_and_comes_last",
        "tests/test_volume_growth.py::test_eyes_become_circles_on_a_cut_near_the_wall",
        "tests/test_volume_dendrites.py::test_upward_bias_turns_branches_vertical",
        "tests/test_volume_dendrites.py::test_slow_wrap_gives_thin_coats_round_plumes",
        "tests/test_volume_dendrites.py::test_plumes_stay_within_their_reach_of_the_wall",
        "tests/test_volume_dendrites.py::test_inclusion_presets_pass_on_their_configured_cut[moss-dense-3d]",
        "tests/test_volume.py::test_staged_cut_shows_wall_floor_wall",
        "tests/test_discriminants.py::test_liesegang_rounds_corners_and_breaks_rings",
        "tests/test_discriminants.py::test_pixel_steps_in_a_traced_outline_are_not_corners",
        "tests/test_discriminants.py::test_settled_layers_thin_where_the_cavity_widens",
        "tests/test_explore.py::test_mechanistic_draws_still_band",
        "tests/test_benchmark.py::test_true_boundaries_marked_on_a_synthetic_photo_are_found",
        "tests/test_sequence.py::test_band_thickness_records_the_supply",
        "tests/test_front_feedback.py::test_a_cavity_that_closes_late_bands_while_open",
        "tests/test_settling.py::test_verification_preset_passes_and_matches_its_preview",
        # Added 2026-11-10 (5 s or more since the list was made):
        "tests/test_features.py::test_bands_around_a_filament_near_a_channel_do_not_fold",
        "tests/test_features.py::test_channel_works_with_a_later_lining_stage",
        "tests/test_features.py::test_the_opening_and_the_clear_layer_do_not_move_the_channel",
        "tests/test_features.py::test_adding_a_channel_leaves_the_others_in_place",
        "tests/test_features.py::test_influence_runs_from_0_to_1_and_ignores_the_bands",
        "tests/test_features.py::test_with_an_opening_the_outer_bands_end_short_of_the_line",
        "tests/test_rim.py::test_real_model_declines_backdrop_only_and_frame_crossing",
        "tests/test_rim.py::test_real_model_finds_synthetic_stones",
    }
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.nodeid in SLOW or item.nodeid.split("[")[0] in SLOW:
            item.add_marker(pytest.mark.slow)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """The app's server on a fresh runs folder, without the built web UI."""
    with TestClient(create_app(tmp_path, static_dir=None)) as c:
        yield c
