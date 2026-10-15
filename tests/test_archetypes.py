from pathlib import Path

import pytest
from pydantic import ValidationError

from agatesim.archetypes import Status, load_registry, to_markdown
from agatesim.archetypes.registry import parse_registry

EXPECTED_LADDER = [
    "fortification",
    "seam",
    "waterline",
    "fortification-waterline",
    "quartz-geode",
    "botryoidal",
    "eye",
    "tube",
    "moss",
    "plume",
    "shadow",
    "iris",
]


def test_shipped_registry_loads_in_ladder_order() -> None:
    registry = load_registry()
    assert [a.id for a in registry.by_rung()] == EXPECTED_LADDER


def test_docs_archetypes_md_is_in_sync(repo_root: Path) -> None:
    on_disk = (repo_root / "docs" / "archetypes.md").read_text("utf-8")
    assert on_disk == to_markdown(load_registry()), (
        "docs/archetypes.md is stale; run: agatesim archetypes --write docs/archetypes.md"
    )


def _registry_toml(*archetypes: str) -> str:
    return "schema_version = 1\n" + "\n".join(archetypes)


def _archetype(
    id: str, rung: int, depends_on: list[str] | None = None, status: str = "pending"
) -> str:
    deps = depends_on or []
    return f"""
[[archetypes]]
id = "{id}"
name = "{id}"
rung = {rung}
status = "{status}"
subsystem = "formation"
hosts = ["volcanic"]
depends_on = {deps!r}
summary = "test"
  [[archetypes.criteria]]
  id = "c"
  description = "d"
  metric = "m"
""".replace("'", '"')


def test_valid_minimal_registry() -> None:
    registry = parse_registry(_registry_toml(_archetype("a", 1), _archetype("b", 2, ["a"])))
    assert registry.get("b").depends_on == ("a",)


@pytest.mark.parametrize(
    ("archetypes", "message"),
    [
        ((_archetype("a", 1), _archetype("a", 2)), "duplicate archetype id"),
        ((_archetype("a", 1, ["missing"]),), "unknown archetype"),
        ((_archetype("a", 2), _archetype("b", 2, ["a"])), "earlier rungs"),
        ((_archetype("a", 2, ["b"]), _archetype("b", 1, ["a"])), "earlier rungs"),
        (
            (_archetype("a", 1), _archetype("b", 2, ["a"], status="verified")),
            "is verified but its dependency",
        ),
    ],
)
def test_invalid_registries_are_rejected(archetypes: tuple[str, ...], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_registry(_registry_toml(*archetypes))


def test_unknown_fields_are_rejected() -> None:
    text = _registry_toml(_archetype("a", 1)).replace('summary = "test"', 'summery = "test"')
    with pytest.raises(ValidationError):
        parse_registry(text)


def test_nothing_is_verified_yet() -> None:
    # Guards against a status being flipped by hand without a passing preset.
    # Remove when the first archetype's criteria are implemented in CI.
    assert all(a.status is not Status.VERIFIED for a in load_registry().archetypes)
