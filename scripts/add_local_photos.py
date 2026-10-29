"""Add photos used by permission to the reference library (tier 2, ADR 0073).

    uv run python scripts/add_local_photos.py FILE... --prefix ID --title TITLE
        --author ALIAS --licence "used by permission: ..." [--stone ID]
        [--names a1 a2 ...] [--dry-run]

Each photo is copied into references/library/ (gitignored) with every piece of
metadata stripped, and listed in references/library.toml under the private
alias, never fetched. Its id is PREFIX-NAME, NAME being the file's stem or the
matching --names entry. Photos of one stone share a `stone` id: --stone for all
of them, otherwise PREFIX and the letters that begin the name (a1, a2 -> a).
The photographer's handle and the permission note belong in the gitignored
references/library-private.toml, never in the list.
"""

from __future__ import annotations

import argparse
import datetime
import io
import re
import sys
from pathlib import Path

from PIL import Image

from agatesim.library import IMAGES_DIR, LIBRARY_TOML, load_library, slug, write_library
from agatesim.specimen.photo import strip_metadata


def _stone(prefix: str, name: str) -> str:
    letters = re.match(r"[a-z]+", name)
    return f"{prefix}-{letters.group(0) if letters else name}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--licence", required=True)
    parser.add_argument("--stone")
    parser.add_argument("--names", nargs="*")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    names = args.names or [slug(f.stem) for f in args.files]
    if len(names) != len(args.files):
        parser.error("--names needs one name per file")
    existing = [e.model_dump(exclude_none=True) for e in load_library().images]
    taken = {e["id"] for e in existing}
    today = datetime.date.today().isoformat()
    entries: list[dict[str, object]] = []
    copies: list[tuple[Path, bytes]] = []
    for path, name in zip(args.files, names, strict=True):
        image_id = f"{args.prefix}-{name}"
        if image_id in taken:
            parser.error(f"{image_id} is already in the library")
        data = strip_metadata(path.read_bytes())
        with Image.open(io.BytesIO(data)) as image:
            harmless = ("jfif", "progress", "icc", "adobe")
            kept = [k for k in map(str, image.info) if not k.startswith(harmless)]
            if len(image.getexif()) or kept:
                parser.error(f"{path.name}: metadata left after stripping: {kept}")
            size = image.size
        stone = args.stone or _stone(args.prefix, name)
        entries.append(
            {
                "id": image_id,
                "title": f"{args.title}, {name}",
                "source": "private (tier 2, ADR 0073)",
                "author": args.author,
                "licence": args.licence,
                "licence_url": "",
                "tier": 2,
                "retrieved": today,
                "stone": stone,
            }
        )
        copies.append((IMAGES_DIR / f"{image_id}.jpg", data))
        print(f"{image_id}  {size[0]}x{size[1]}  stone {stone}", file=sys.stderr)
    if args.dry_run:
        return 0
    write_library(existing + entries)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for target, data in copies:
        target.write_bytes(data)
    print(f"added {len(entries)} photos to {LIBRARY_TOML}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
