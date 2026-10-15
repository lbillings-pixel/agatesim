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


def test_run_preset_writes_a_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "seam", "--resolution", "160", "--out", str(tmp_path), "--check"]) == 0
    out = capsys.readouterr().out
    assert "seam: PASSED" in out
    (run_dir,) = tmp_path.iterdir()
    assert (run_dir / "slab.png").exists()


def test_run_check_fails_on_failing_criteria(tmp_path: Path) -> None:
    config = tmp_path / "bad.toml"
    config.write_text(
        'name = "bad"\narchetype = "waterline"\n[grid]\nresolution = 160\n'
        '[cavity]\npreset = "nodule-angular"\n[model]\nkind = "procedural-fortification"\n',
        encoding="utf-8",
    )
    assert main(["run", str(config), "--out", str(tmp_path / "runs"), "--check"]) == 1


def test_listing_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cavities"]) == 0
    assert "nodule-angular" in capsys.readouterr().out
    assert main(["presets"]) == 0
    assert "waterline" in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("agatesim ")
