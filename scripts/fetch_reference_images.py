"""Fetch full-resolution reference photos into references/images/full/ (gitignored).

    uv run python scripts/fetch_reference_images.py

The repository keeps reduced copies and attribution (references/images/
catalogue.toml); the full files are large, so they are fetched on demand from
Wikimedia Commons, by file title, and checked against their published size.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "references" / "images" / "full"
API = "https://commons.wikimedia.org/w/api.php"
AGENT = "agatesim-reference-fetch/0.1 (https://github.com/lbillings-pixel/agatesim)"

# Corner benchmark (ADR 0026): polyhedral agates from Sítio Garguelo, Brazil,
# photographed by Marie-Lan Taÿ Pamart (CC BY 4.0), MNHN Caillois donation.
FILES = [
    "Polyhedral agate Caillois Donation MNHN n01.jpg",
    "Polyhedral agate Caillois Donation MNHN n02.jpg",
    "Polyhedral agate Caillois Donation MNHN n03.jpg",
    "Polyhedral agate Caillois Donation MNHN n04.jpg",
    "Polygonal agate Sítio Garguelo Caillois Donation MNHN.jpg",
]


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _info(title: str) -> dict[str, object]:
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "titles": f"File:{title}",
            "prop": "imageinfo",
            "iiprop": "url|size|sha1",
            "format": "json",
        }
    )
    pages = json.loads(_get(f"{API}?{query}"))["query"]["pages"]
    page = next(iter(pages.values()))
    return page["imageinfo"][0]


def local_name(title: str) -> str:
    return title.lower().replace(" ", "-").replace("í", "i")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for title in FILES:
        path = OUT / local_name(title)
        info = _info(title)
        if path.exists() and path.stat().st_size == info["size"]:
            print(f"have    {path.name}")
            continue
        data = _get(str(info["url"]))
        if len(data) != info["size"]:
            print(f"size mismatch for {title}: {len(data)} != {info['size']}", file=sys.stderr)
            return 1
        path.write_bytes(data)
        print(f"fetched {path.name} ({len(data) / 1e6:.1f} MB, {info['width']}x{info['height']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
