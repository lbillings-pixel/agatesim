"""Randomize (ADR 0051): key settings move within bounded ranges; mechanistic
draws are checked so they still band."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from agatesim.config import load_preset
from agatesim.explore import MIN_BANDS, randomize, vary
from agatesim.fields import Phase
from agatesim.models import FrontFeedback
from agatesim.server.app import create_app
from agatesim.simulate import simulate


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(tmp_path, static_dir=None)) as c:
        yield c


def _ranges(model: BaseModel) -> list[tuple[list[str], dict[str, Any], dict[str, Any]]]:
    """(path, explore range, property) for every setting with a range."""
    schema = type(model).model_json_schema()
    out: list[tuple[list[str], dict[str, Any], dict[str, Any]]] = []

    def walk(props: dict[str, Any], path: list[str]) -> None:
        for key, prop in props.items():
            ref = prop.get("$ref")
            if isinstance(ref, str):
                walk(schema["$defs"][ref.split("/")[-1]]["properties"], [*path, key])
            elif "explore" in prop:
                out.append(([*path, key], prop["explore"], prop))

    walk(schema["properties"], [])
    return out


def _get(values: dict[str, Any], path: list[str]) -> Any:
    for key in path:
        values = cast(dict[str, Any], values[key])
    return values


@pytest.mark.parametrize(
    "name",
    ["fortification", "waterline", "botryoidal", "fortification-mechanistic", "stick-mechanistic"],
)
def test_draws_stay_in_their_ranges_and_limits(name: str) -> None:
    config = load_preset(name)
    ranges = _ranges(config.model)
    assert ranges, "every randomizable model has key settings with ranges"
    rng = np.random.default_rng(0)
    before = config.model.model_dump(mode="json")
    for _ in range(25):
        after = vary(config, 1.0, rng).model.model_dump(mode="json")
        for path, spec, prop in ranges:
            v, v0 = _get(after, path), _get(before, path)
            assert min(spec["min"], v0) - 1e-12 <= v <= max(spec["max"], v0) + 1e-12, path
            if "minimum" in prop:
                assert v >= prop["minimum"], path
            if "maximum" in prop:
                assert v <= prop["maximum"], path


def test_strength_zero_changes_only_the_seed() -> None:
    config = load_preset("fortification")
    drawn = vary(config, 0.0, np.random.default_rng(1))
    assert drawn.model == config.model
    assert drawn.seed != config.seed


def test_draws_repeat_with_the_same_seed() -> None:
    config = load_preset("botryoidal")
    a = randomize(config, 0.7, seed=5).config
    b = randomize(config, 0.7, seed=5).config
    assert a == b
    assert a.model != config.model


def test_mechanistic_draws_still_band() -> None:
    """Every accepted H1 draw lays at least MIN_BANDS bands in a quick run."""
    config = load_preset("fortification-mechanistic")
    for seed in range(3):
        draw = randomize(config, 1.0, seed=seed)
        assert draw.checked
        assert draw.accepted
        assert isinstance(draw.config.model, FrontFeedback)
        f = simulate(draw.config.with_resolution(192)).fields
        agate = (f.phase == Phase.CHALCEDONY) & (f.band >= 0)
        assert len(np.unique(f.band[agate])) >= MIN_BANDS


def test_procedural_draws_need_no_check() -> None:
    draw = randomize(load_preset("fortification"), 1.0, seed=2)
    assert not draw.checked
    assert draw.accepted
    assert draw.attempts == 1


def test_the_randomize_endpoint_returns_valid_settings(client: TestClient) -> None:
    config = load_preset("waterline").model_dump(mode="json")
    body = client.post("/api/randomize", json={"config": config, "strength": 0.5, "seed": 3}).json()
    assert body["accepted"] is True
    assert body["config"]["model"] != config["model"]
    assert body["config"]["model"]["kind"] == "procedural-waterline"
