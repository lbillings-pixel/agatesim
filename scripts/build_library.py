"""Build the reference library's sources list (references/library.toml) from
Wikimedia Commons (ADR 0063, tier 1; ADR 0066).

    uv run python scripts/build_library.py [--limit 300] [--dry-run]

Walks a curated set of agate categories, keeps openly licensed photos large
enough to classify, and records each one's source, author, licence and the
forms its title and categories suggest (guesses for the labelling screen, not
labels). Only metadata is read here; `agatesim library fetch` fetches images.
Entries already in the list are kept as they are, so ids and labels stay put.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

from agatesim.library import (
    LIBRARY_TOML,
    guess_forms,
    load_library,
    open_licence,
    slug,
    write_library,
)

API = "https://commons.wikimedia.org/w/api.php"
AGENT = "agatesim-library/0.1 (https://github.com/lbillings-pixel/agatesim)"
THUMB_PX = 1280  # a standard Commons thumbnail width (others are served larger)
MIN_SIDE_PX = 800
DEPTH = 3
PAUSE_S = 1.5  # between requests: Commons rate-limits faster clients

# Categories of agate specimens. Objects, art, jewellery and dyed stones are
# left out: they show the stone worked or coloured, not as it formed.
ROOTS = [
    "Category:Banded agates",
    "Category:Moss agate",
    "Category:Tube agates",
    "Category:Agate nodules",
    "Category:Agate textures",
    "Category:Agate in chert",
    "Category:Enhydro agates",
    "Category:Ruin agate",
    "Category:Fire agate",
    "Category:Agates by country",
    "Category:Agates in the Ural Geological Museum",
    "Category:Agate, physical properties and origin",
    "Category:Plume agate",
    "Category:Iris agate",
    "Category:Lace agate",
    "Category:Fortification agate",
    "Category:Eye agate",
    "Category:Agate geodes",
]
SKIP = re.compile(
    r"jewel|ring\b|rings\b|bead|cameo|intaglio|\bart\b|object|vessel|bowl|cup|seal|"
    r"carv|dyed|sardonyx|necklace|pendant|brooch|amulet|box|snuff|vase|mosaic|"
    r"cabochon|knife|handle|button|map|stamp|coin|building|street|people|portrait",
    re.IGNORECASE,
)


def _get(params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode({**params, "format": "json", "maxlag": 5})
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": AGENT})
    for attempt in range(6):
        time.sleep(PAUSE_S)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read())
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(float(e.headers.get("Retry-After") or 30 * (attempt + 1)))
            continue
        if data.get("error", {}).get("code") != "maxlag":
            return data
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("Commons is busy or rate-limiting; try again later")


def _members(category: str, kind: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    params: dict[str, Any] = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmtype": kind,
        "cmlimit": 500,
    }
    while True:
        data = _get(params)
        out.extend(data["query"]["categorymembers"])
        if "continue" not in data:
            return out
        params.update(data["continue"])


def _walk() -> dict[str, list[str]]:
    """File titles under the roots, each with the categories it was found in."""
    files: dict[str, list[str]] = {}
    seen: set[str] = set()
    queue = [(c, 0) for c in ROOTS]
    while queue:
        category, depth = queue.pop(0)
        if category in seen or SKIP.search(category):
            continue
        seen.add(category)
        try:
            for f in _members(category, "file"):
                files.setdefault(f["title"], []).append(category.removeprefix("Category:"))
            if depth < DEPTH:
                queue.extend((s["title"], depth + 1) for s in _members(category, "subcat"))
        except KeyError:
            continue  # a category that doesn't exist
    return files


def _plain(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def _info(titles: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(titles), 50):
        data = _get(
            {
                "action": "query",
                "titles": "|".join(titles[i : i + 50]),
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": THUMB_PX,
                "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|Credit",
            }
        )
        for page in data["query"]["pages"].values():
            if "imageinfo" in page:
                out[page["title"]] = page["imageinfo"][0]
    return out


def _entry(
    title: str, info: dict[str, Any], categories: list[str], today: str
) -> dict[str, Any] | None:
    meta = {k: v.get("value", "") for k, v in info.get("extmetadata", {}).items()}
    licence = _plain(meta.get("LicenseShortName", ""))
    author = _plain(meta.get("Artist", "")) or _plain(meta.get("Credit", ""))
    if info.get("mime") not in ("image/jpeg", "image/png") or not open_licence(licence):
        return None
    if min(info["width"], info["height"]) < MIN_SIDE_PX or not author or SKIP.search(title):
        return None
    name = title.removeprefix("File:")
    return {
        "id": slug(name),
        "title": name,
        "source": info["descriptionurl"],
        "url": (info.get("thumburl") or info["url"]).split("?")[0],
        "author": author[:200],
        "licence": licence,
        "licence_url": meta.get("LicenseUrl", "") or info["descriptionurl"],
        "tier": 1,
        "retrieved": today,
        "categories": sorted(set(categories))[:8],
        "guesses": guess_forms(name, categories),
    }


def _pick(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Up to `limit` entries, rarest guessed form first so every form is
    represented, in a stable order (a hash of the id) within each form."""
    counts = Counter(g for c in candidates for g in c["guesses"])

    def rarity(c: dict[str, Any]) -> tuple[int, str]:
        rarest = min((counts[g] for g in c["guesses"]), default=10**9)
        return rarest, hashlib.sha1(c["id"].encode()).hexdigest()

    per_form: Counter[str] = Counter()
    cap = max(10, limit // 8)  # no form takes more than an eighth unless room is left
    first: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for c in sorted(candidates, key=rarity):
        top = min(c["guesses"], key=lambda g: counts[g]) if c["guesses"] else ""
        (first if per_form[top] < cap else rest).append(c)
        per_form[top] += 1
    return (first + rest)[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    existing = list(load_library().images) if LIBRARY_TOML.exists() else []
    have = {e.title for e in existing}
    files = _walk()
    print(f"{len(files)} files under {len(ROOTS)} root categories", file=sys.stderr)
    titles = [t for t in files if t.removeprefix("File:") not in have]
    infos = _info(titles)
    today = datetime.date.today().isoformat()
    candidates = [
        e for t, i in infos.items() if (e := _entry(t, i, files.get(t, []), today)) is not None
    ]
    ids = {e.id for e in existing}
    candidates = [c for c in candidates if c["id"] not in ids]
    print(f"{len(candidates)} open-licence photos qualify", file=sys.stderr)
    chosen = _pick(candidates, max(0, args.limit - sum(e.tier == 1 for e in existing)))
    for c in chosen:  # titles that differ only in case or punctuation share a slug
        base, n = c["id"], 2
        while c["id"] in ids:
            c["id"], n = f"{base}-{n}", n + 1
        ids.add(c["id"])
    counts = Counter(g for c in chosen for g in c["guesses"] or ["(none)"])
    print("guessed forms:", dict(counts.most_common()), file=sys.stderr)
    if args.dry_run:
        return 0
    entries = [e.model_dump(exclude_none=True) for e in existing] + chosen
    write_library(entries)
    print(f"wrote {len(entries)} entries to {LIBRARY_TOML}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
