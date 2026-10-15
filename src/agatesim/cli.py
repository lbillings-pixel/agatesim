"""Command-line interface: `agatesim ...`."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from agatesim import __version__
from agatesim.archetypes import load_registry, to_markdown

PREVIEW_RESOLUTION = 256


def _cmd_archetypes(args: argparse.Namespace) -> int:
    registry = load_registry()
    if args.write is not None:
        path: Path = args.write
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_markdown(registry), encoding="utf-8", newline="\n")
        print(f"wrote {path}")
        return 0
    print(f"{'rung':>4}  {'procedural':<12} {'mechanistic':<12} {'archetype':<24} subsystem")
    for a in registry.by_rung():
        deps = f"  (needs {', '.join(a.depends_on)})" if a.depends_on else ""
        print(
            f"{a.rung:>4}  {a.status.procedural.value:<12} {a.status.mechanistic.value:<12} "
            f"{a.id:<24} {a.subsystem.value}{deps}"
        )
    return 0


def _cmd_cavities(_: argparse.Namespace) -> int:
    from agatesim.geometry import CAVITY_PRESETS

    for p in CAVITY_PRESETS.values():
        print(f"{p.name:<18} {p.host.value:<12} {p.description}")
    return 0


def _cmd_presets(_: argparse.Namespace) -> int:
    from agatesim.config import load_preset, preset_names

    for name in preset_names():
        c = load_preset(name)
        print(f"{name:<16} {c.model.kind:<26} cavity={c.cavity.preset}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from agatesim.config import load_config, load_preset
    from agatesim.runs import write_run
    from agatesim.simulate import simulate

    source = Path(args.config)
    config = load_config(source) if source.suffix == ".toml" else load_preset(args.config)
    if args.preview:
        config = config.with_resolution(PREVIEW_RESOLUTION)
    if args.resolution is not None:
        config = config.with_resolution(args.resolution)

    started = datetime.now().astimezone()
    t0 = time.perf_counter()
    result = simulate(config)
    record = write_run(result, args.out, started=started, elapsed_s=time.perf_counter() - t0)
    print(f"run written to {record.path}")
    if record.evaluation is None:
        return 0
    ev = record.evaluation
    for r in ev.results:
        mark = "PASS" if r.passed else "FAIL"
        value = "n/a" if r.value is None else f"{r.value:.4g}"
        print(f"  {mark}  {r.id:<22} {value:>10}  {r.detail}")
    print(f"{ev.archetype}: {'PASSED' if ev.passed else 'FAILED'}")
    return 0 if ev.passed or not args.check else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agatesim", description=__doc__)
    parser.add_argument("--version", action="version", version=f"agatesim {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("archetypes", help="list the archetype ladder")
    p.add_argument("--write", type=Path, metavar="PATH", help="write the ladder as markdown")
    p.set_defaults(func=_cmd_archetypes)

    p = sub.add_parser("cavities", help="list the preset cavity shapes")
    p.set_defaults(func=_cmd_cavities)

    p = sub.add_parser("presets", help="list the shipped run presets")
    p.set_defaults(func=_cmd_presets)

    p = sub.add_parser("run", help="run a simulation from a preset name or a config .toml")
    p.add_argument("config", help="preset name (see `agatesim presets`) or path to a .toml")
    p.add_argument("--out", type=Path, default=Path("runs"), help="runs directory (default: runs)")
    p.add_argument("--preview", action="store_true", help=f"{PREVIEW_RESOLUTION}px quick preview")
    p.add_argument("--resolution", type=int, help="override grid resolution")
    p.add_argument("--check", action="store_true", help="exit 1 if archetype criteria fail")
    p.set_defaults(func=_cmd_run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
