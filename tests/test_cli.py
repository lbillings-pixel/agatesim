from pathlib import Path

import pytest

from agatesim.archetypes import load_registry, to_markdown
from agatesim.cli import main


def test_archetypes_lists_every_rung(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["archetypes"]) == 0
    out = capsys.readouterr().out
    for a in load_registry().archetypes:
        assert a.id in out


def test_archetypes_write(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "archetypes.md"
    assert main(["archetypes", "--write", str(target)]) == 0
    assert target.read_bytes() == to_markdown(load_registry()).encode("utf-8")


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("agatesim ")
