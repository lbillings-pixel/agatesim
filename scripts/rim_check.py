# pyright: basic
"""The rim-finder on the library (ADR 0073 section 3, ADR 0074).

uv run --no-sync python scripts/rim_check.py split
    fix the seeded split once: 80 tuning, 150 held out (nodule's 30
    owner-checked photos among them), the tier-2 photos as a hard set;
    written to references/rim-split.toml
uv run --no-sync python scripts/rim_check.py run tune|held|friend [--tau T] [--b]
    find the rim on one set (with the segmentation model where fetched; --b
    keeps to method B); outlines drawn on each photo (no metadata), results.json
    (with the model's scores) and masks.npz written to runs/rim-check/<set>[-<tag>]/
uv run --no-sync python scripts/rim_check.py score tune [--tag T]
    score a run against the helpers' judgments (runs/rim-check/judge-*.json):
    an outline matching a judged one (IoU >= 0.95) inherits its answer
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from agatesim.library import load_labels, load_library
from agatesim.maps import OnnxPatchEmbedder, PatchCache, library_patches
from agatesim.specimen import rim as rim_module
from agatesim.specimen.photo import load_photo
from agatesim.specimen.rim import TAU, find_rim
from agatesim.specimen.sam import Sam

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "references" / "rim-split.toml"
OUT = ROOT / "runs" / "rim-check"
NODULE_LABELS = ROOT.parent / "nodule" / "references" / "library-view-labels.toml"
SEED = 73
TUNE = 80
VIEW_PX = 768  # long side of the drawn outlines


def split(force: bool) -> None:
    if SPLIT.exists() and not force:
        sys.exit(f"{SPLIT} exists: the split is fixed before tuning (--force to redo)")
    library, labels = load_library(), load_labels()
    usable = sorted(
        i.id
        for i in library.images
        if i.tier == 1 and i.id in labels and labels[i.id].verdict != "unusable"
    )
    checked = set(tomllib.loads(NODULE_LABELS.read_text("utf-8"))["meta"]["check_sample"])
    assert checked <= set(usable), sorted(checked - set(usable))
    # Photos of one stone stay together (only tier 2 records stones so far).
    stones = {i.id: i.stone or i.id for i in library.images}
    groups = sorted({stones[i] for i in usable if i not in checked})
    rng = np.random.default_rng(SEED)
    order = [groups[k] for k in rng.permutation(len(groups))]
    tune: list[str] = []
    for g in order:
        members = [i for i in usable if stones[i] == g]
        if len(tune) + len(members) <= TUNE:
            tune += members
    held = sorted(set(usable) - set(tune))
    friend = sorted(i.id for i in library.images if i.tier == 2)
    lines = [
        "# The rim-finder's split (ADR 0073 section 3), drawn once with seed "
        f"{SEED} by scripts/rim_check.py.",
        "# Settings are tuned on `tune` only; `held` includes nodule's 30 owner-checked",
        "# photos; `friend` (tier 2) is a hard test set, never used for tuning.",
        f"seed = {SEED}",
    ]
    for name, ids in (("tune", sorted(tune)), ("held", held), ("friend", friend)):
        lines.append(f"{name} = [")
        lines += [f'    "{i}",' for i in ids]
        lines.append("]")
    SPLIT.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"tune {len(tune)}, held {len(held)}, friend {len(friend)} -> {SPLIT}")


def draw(rgb: np.ndarray, outline: np.ndarray, caption: str) -> Image.Image:
    im = Image.fromarray(rgb).convert("RGB")
    scale = VIEW_PX / max(im.size)
    im = im.resize((round(im.width * scale), round(im.height * scale)))
    d = ImageDraw.Draw(im)
    if len(outline):
        pts = [
            (float(x) * scale, float(y) * scale)
            for x, y in outline[:: max(1, len(outline) // 2000)]
        ]
        d.line([*pts, pts[0]], fill=(255, 0, 255), width=3)
    d.rectangle((0, 0, 8 * len(caption) + 8, 18), fill=(0, 0, 0))
    d.text((4, 3), caption, fill=(255, 255, 255))
    return im


MASK_PX = 256  # long side of the saved masks
SAME = 0.95  # IoU at which two outlines of a photo count as the same


def run(name: str, tau: float, tag: str, method_b: bool) -> None:
    ids = tomllib.loads(SPLIT.read_text("utf-8"))[name]
    library = load_library()
    cache = PatchCache(OnnxPatchEmbedder())
    model = None if method_b else Sam()
    out = OUT / (f"{name}-{tag}" if tag else name)
    out.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, object]] = {}
    masks: dict[str, np.ndarray] = {}
    start = time.perf_counter()
    for k, image_id in enumerate(ids, 1):
        image = library.get(image_id)
        rgb = load_photo(image.path.read_bytes(), 1024).rgb
        rim = find_rim(rgb, patches=library_patches(cache, image), tau=tau, sam=model)
        results[image_id] = {
            "reason": rim.reason,
            "area": float(rim.mask.mean()),
            "scores": rim.scores,
        }
        small = Image.fromarray(rim.mask)
        small.thumbnail((MASK_PX, MASK_PX), Image.Resampling.NEAREST)
        masks[image_id] = np.asarray(small, dtype=bool)
        caption = "outline" if rim.found else f"no outline: {rim.reason}"
        draw(rgb, rim.outline, caption).save(out / f"{image_id}.png")
        if k % 20 == 0:
            print(f"{k}/{len(ids)}", flush=True)
    settings = {"tau": tau, "method": "B" if method_b else "C"}
    (out / "results.json").write_text(json.dumps({**settings, "results": results}, indent=1))
    np.savez_compressed(out / "masks.npz", **masks)  # pyright: ignore[reportArgumentType]
    found = sum(r["reason"] is None for r in results.values())
    took = time.perf_counter() - start
    print(f"{name}: outline on {found}/{len(ids)}, {took:.0f} s -> {out}")


def score(name: str, tag: str) -> None:
    """Counts against ADR 0073's bar, from the judgments so far. A judgment
    belongs to the run it was made on (its `run` key, the run folder name)."""
    out = OUT / (f"{name}-{tag}" if tag else name)
    results = json.loads((out / "results.json").read_text())["results"]
    masks = np.load(out / "masks.npz")
    in_frame: dict[str, bool] = {}
    judged: list[tuple[str, np.ndarray, bool]] = []  # (id, mask, follows)
    for path in sorted(OUT.glob("judge-*.json")):
        data = json.loads(path.read_text())
        run_dir = OUT / data.pop("_run", name)
        old = np.load(run_dir / "masks.npz") if (run_dir / "masks.npz").exists() else None
        for image_id, j in data.items():
            in_frame[image_id] = j["rim_in_frame"] == "yes"
            if j["outline_follows"] != "na" and old is not None and image_id in old:
                judged.append((image_id, old[image_id], j["outline_follows"] == "yes"))
    follows, unknown = 0, []
    for image_id, r in results.items():
        if r["reason"] is not None:
            continue
        m = masks[image_id]
        # The closest judged outline, so a judgment of this very outline wins.
        overlaps = [
            ((m & o).sum() / max((m | o).sum(), 1), f) for i, o, f in judged if i == image_id
        ]
        best = max(overlaps, default=(0.0, None), key=lambda t: t[0])
        verdict = best[1] if best[0] >= SAME else None
        if verdict is None:
            unknown.append(image_id)
        else:
            follows += verdict
    found = [i for i, r in results.items() if r["reason"] is None]
    rim_in = [i for i in results if in_frame.get(i)]
    rim_out = [i for i in results if i in in_frame and not in_frame[i]]
    known = len(found) - len(unknown)
    print(
        f"{out.name}: {len(found)} outlines; follow the rim {follows}/{known} judged"
        f" ({len(unknown)} not yet judged)"
    )
    print(
        f"  outline on {sum(i in found for i in rim_in)}/{len(rim_in)} rim-in-frame photos;"
        f" declined {sum(i not in found for i in rim_out)}/{len(rim_out)} cut-off photos"
    )
    if unknown:
        (out / "unjudged.txt").write_text("".join(f"{i}.png\n" for i in unknown))
        print(f"  list of unjudged outlines -> {out / 'unjudged.txt'}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("--force", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("set", choices=("tune", "held", "friend"))
    r.add_argument("--tau", type=float, default=TAU)
    r.add_argument("--tag", default="")
    r.add_argument("--b", action="store_true", help="method B only, without the model")
    r.add_argument("--param", action="append", default=[], help="NAME=VALUE, a rim setting")
    c = sub.add_parser("score")
    c.add_argument("set", choices=("tune", "held", "friend"))
    c.add_argument("--tag", default="")
    a = p.parse_args()
    if a.cmd == "split":
        split(a.force)
    elif a.cmd == "run":
        for item in a.param:
            key, value = item.split("=")
            setattr(rim_module, key, type(getattr(rim_module, key))(value))
        run(a.set, a.tau, a.tag, a.b)
    else:
        score(a.set, a.tag)


if __name__ == "__main__":
    main()
