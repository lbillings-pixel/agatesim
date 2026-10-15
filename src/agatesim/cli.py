"""Command-line interface: `agatesim ...`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from agatesim import __version__
from agatesim.archetypes import load_registry, to_markdown


def _cmd_archetypes(args: argparse.Namespace) -> int:
    registry = load_registry()
    if args.write is not None:
        path: Path = args.write
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_markdown(registry), encoding="utf-8", newline="\n")
        print(f"wrote {path}")
        return 0
    for a in registry.by_rung():
        deps = f"  (needs {', '.join(a.depends_on)})" if a.depends_on else ""
        print(f"{a.rung:>3}  {a.status.value:<12} {a.id:<24} {a.subsystem.value}{deps}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agatesim", description=__doc__)
    parser.add_argument("--version", action="version", version=f"agatesim {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("archetypes", help="list the archetype ladder")
    p.add_argument("--write", type=Path, metavar="PATH", help="write the ladder as markdown")
    p.set_defaults(func=_cmd_archetypes)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
