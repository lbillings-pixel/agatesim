"""Band shape on random cuts through each 3D model, blurred like photos: the
models' side of calibration without a ruler (ADR 0069, step 3).

For each 3D preset, settings are drawn from the model's Randomize ranges
(`explore.vary_model`, at full strength), and each draw is cut at random planes
(`volume.slicing.random_cuts`), as slabs are cut wherever the saw went. Each cut
is rendered, then made to look like one library photo picked at random:

- **blur**: the cut is blurred until its edge width over its band spacing is
  that photo's. A photo can't show bands thinner than its edges, and blur
  erases the finest bands, which widens the spacing left behind; so the blur
  is found in a few rounds, re-measuring the spacing after each.
- **noise**: grey noise of the photo's measured noise level is added.

The cut is then measured by `specimen.shape`, as photos are, with the face its
cavity and the quartz core share read from the quartz phase. Results are cached
per preset in `CUT_SHAPES_PATH` (gitignored, beside the library's).

The noise is drawn per pixel of the cut, so it depends on the cut's resolution,
as a photo's does on its own; it is not part of any model.
"""

from __future__ import annotations

import hashlib
import json
import math
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import ValidationError

from agatesim import _rd, _scipy, progress
from agatesim.explore import UNCHECKED, vary_model
from agatesim.fields import Phase
from agatesim.maps import MODELS_DIR
from agatesim.render import render_slab
from agatesim.shapes import STATISTICS, Spread
from agatesim.specimen.quality import (
    PROFILE_SMOOTH_PX,
    Quality,
    assess,
    badge,
    half_max_width,
    luminance,
)
from agatesim.specimen.segment import trace_outline
from agatesim.specimen.shape import measure
from agatesim.volume.config import VolumeConfig, load_volume_preset
from agatesim.volume.simulate import prepare_volume
from agatesim.volume.slicing import random_cuts

CUT_SHAPES_PATH = MODELS_DIR / "cut-shapes.json"
VERSION = 2  # raise when the blur, the cuts or the statistics change
DRAWS = 12  # settings drawn per model
CUTS = 2  # random cuts per draw
PROBE_RESOLUTION = 512  # pixels across the first, quick look at a cut
MAX_RESOLUTION = 3072  # most pixels across a cut
MIN_RESOLUTION = 256
# A cut is sized so its bands are as many pixels apart as its photo's, and at
# least this many times the spacing at which the gate's sharpest edge would
# already be the photo's share of it.
SHARP_MARGIN = 1.3
BLUR_ROUNDS = 4  # rounds of blurring and re-measuring the band spacing
SPACING_SETTLED = 0.05  # stop when the spacing changes by less than this share
# A cut matches its photo when its edge per spacing is within this share of the
# photo's. Cuts too coarse for a sharp photo (even unblurred, the gate's sharpest
# edge is a large share of a few-pixel spacing) don't, and aren't compared.
MATCH_TOLERANCE = 0.15
MAX_SIGMA = 40.0  # px
MAX_REDRAWS = 5  # draws a 3D config rejects before the model is given up on
LEVELS = ("fit", "borderline")


@dataclass(frozen=True)
class Look:
    """What a library photo's edges and noise look like, without a scale."""

    photo: str
    edge_per_spacing: float
    noise: float  # grey levels
    spacing_px: float  # its band spacing, which a cut is sized to show alike


def looks(entries: dict[str, dict[str, object]]) -> list[Look]:
    """The fit and borderline photos whose edge, spacing and noise were measured."""
    out: list[Look] = []
    for photo, e in sorted(entries.items()):
        edge, spacing, noise = _number(e, "edge_px"), _number(e, "spacing_px"), _number(e, "noise")
        if e.get("level") not in LEVELS or edge is None or spacing is None or noise is None:
            continue
        if spacing > 0:
            out.append(Look(photo, edge / spacing, noise, spacing))
    return out


def _number(entry: dict[str, object], key: str) -> float | None:
    v = entry.get(key)
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
        return float(v)
    return None


def _settings(entry: dict[str, object]) -> dict[str, float]:
    s = entry.get("settings")
    return cast(dict[str, float], s) if isinstance(s, dict) else {}


def edge_of_blur(sigma: float) -> float:
    """Edge width (px) the quality gate measures across a sharp step blurred by
    a Gaussian of `sigma` px (`quality.rim_width`'s smoothing and half-max width)."""
    x = np.arange(-160, 161)
    step = (x >= 0).astype(np.float64)
    if sigma > 0:
        step = _scipy.gaussian(step, sigma)
    width = half_max_width(np.abs(np.gradient(_scipy.gaussian(step, PROFILE_SMOOTH_PX))))
    assert width is not None
    return width[0]


def sigma_for_edge(edge_px: float) -> float:
    """The blur (px) that gives a sharp step an edge width of `edge_px`; 0 when
    a sharp step is already as wide."""
    if edge_px <= edge_of_blur(0.0):
        return 0.0
    lo, hi = 0.0, MAX_SIGMA
    if edge_px >= edge_of_blur(hi):
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if edge_of_blur(mid) < edge_px else (lo, mid)
    return (lo + hi) / 2


def photo_like(
    rgb: NDArray[np.uint8], sigma: float, noise: float, rng: np.random.Generator
) -> NDArray[np.uint8]:
    """`rgb` blurred by `sigma` px, with grey noise of `noise` grey levels, in 8 bits."""
    out = _scipy.gaussian_rgb(rgb, sigma) if sigma > 0 else rgb.astype(np.float64)
    out += rng.normal(0.0, noise, size=rgb.shape[:2])[..., None]
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def measure_cut(
    rgb: NDArray[np.uint8],
    mask: NDArray[np.bool_],
    quartz: NDArray[np.bool_],
    look: Look,
    rng: np.random.Generator,
) -> dict[str, object]:
    """Blur and roughen a rendered cut like `look`'s photo, then measure its band
    shape. `mask` is the face (the cavity) and `quartz` its quartz phase."""
    outline = trace_outline(mask)
    entry: dict[str, object] = {"photo": look.photo, "target": round(look.edge_per_spacing, 4)}
    entry["core"] = round(float(quartz[mask].mean()), 4) if mask.any() else None
    q = assess(rgb, mask, outline)
    if q.band_spacing_px is None or len(outline) < 3:
        return {**entry, "level": "not fit", "bands": False}
    spacing = q.band_spacing_px
    entry["sharp_spacing_px"] = round(spacing, 3)
    noise_rng, measure_seed = rng.spawn(2)
    target = look.edge_per_spacing
    best: tuple[float, float, NDArray[np.uint8], Quality, float] | None = None
    for _ in range(BLUR_ROUNDS):
        sigma = sigma_for_edge(target * spacing)
        seen = photo_like(rgb, sigma, look.noise, np.random.default_rng(noise_rng.integers(2**63)))
        q = assess(seen, mask, outline)
        if q.band_spacing_px is None:
            break
        achieved = edge_of_blur(sigma) / q.band_spacing_px
        if best is None or abs(achieved - target) < abs(best[0] - target):
            best = (achieved, sigma, seen, q, q.band_spacing_px)
        settled = abs(q.band_spacing_px - spacing) < SPACING_SETTLED * spacing
        spacing = q.band_spacing_px
        if settled:
            break
    if best is None:  # the blur erased the bands
        return {**entry, "level": "not fit", "bands": False}
    achieved, sigma, seen, q, spacing = best
    entry.update(
        sigma_px=round(sigma, 3),
        spacing_px=round(spacing, 3),
        achieved=round(achieved, 4),
        matched=abs(achieved - target) <= MATCH_TOLERANCE * target,
        level=badge(q, "shape").level,
        bands=True,
    )
    s = measure(luminance(seen), mask, 1.0, q.noise, spacing, rng=measure_seed)
    entry.update(s.to_json())
    return entry


def resolution_for(rgb: NDArray[np.uint8], mask: NDArray[np.bool_], look: Look, most: int) -> int:
    """Pixels across a cut that show its bands as `look`'s photo shows its own,
    from a first look at the cut (`rgb`, `mask`) at `PROBE_RESOLUTION`."""
    outline = trace_outline(mask)
    if len(outline) < 3:
        return PROBE_RESOLUTION
    spacing = assess(rgb, mask, outline).band_spacing_px
    if spacing is None:
        return PROBE_RESOLUTION
    wanted = max(look.spacing_px, SHARP_MARGIN * edge_of_blur(0.0) / look.edge_per_spacing)
    return int(np.clip(round(PROBE_RESOLUTION * wanted / spacing), MIN_RESOLUTION, most))


def _flat(values: dict[str, Any], prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    for k, v in values.items():
        if isinstance(v, dict):
            out.update(_flat(cast(dict[str, Any], v), f"{prefix}{k}."))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[prefix + k] = float(v)
    return out


def _draw(config: VolumeConfig, rng: np.random.Generator) -> VolumeConfig | None:
    """The preset with its model's settings drawn from their ranges and a new seed."""
    for _ in range(MAX_REDRAWS):
        model = vary_model(config.model, 1.0, rng)
        seed = int(rng.integers(0, 1_000_000))
        data = config.model_dump(mode="json")
        data.update(model=model.model_dump(mode="json"), seed=seed)
        try:
            return VolumeConfig.model_validate(data)
        except ValidationError:
            continue
    return None


def _key(config: VolumeConfig, draws: int, cuts: int, resolution: int, n_looks: int) -> str:
    # The model's schema holds its Randomize ranges, so widening one redoes the cuts.
    schema = type(config.model).model_json_schema()
    text = json.dumps([config.model_dump(mode="json"), schema], sort_keys=True)
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    return f"{VERSION}:{digest}:{draws}:{cuts}:{resolution}:{n_looks}"


def survey_preset(
    name: str,
    photo_looks: list[Look],
    *,
    draws: int = DRAWS,
    cuts: int = CUTS,
    resolution: int = MAX_RESOLUTION,
    seed: int = 0,
) -> list[dict[str, object]]:
    """Every cut's entry for one 3D preset: its draw's settings, the photo it was
    made to look like, and its band shape. Cuts take at most `resolution` pixels
    across."""
    config = load_volume_preset(name)
    if config.model.kind in UNCHECKED:  # no ranges to draw from (explore.UNCHECKED)
        draws = 1
    rng = np.random.default_rng([seed, zlib.crc32(name.encode())])
    draw_rng, cut_rng, look_rng, measure_rng = rng.spawn(4)
    out: list[dict[str, object]] = []
    for d in range(draws):
        progress.report(d / draws, f"{name}: settings draw {d + 1} of {draws}")
        drawn = config if config.model.kind in UNCHECKED else _draw(config, draw_rng)
        if drawn is None:
            out.append({"draw": d, "error": "no valid draw"})
            continue
        settings = _flat(drawn.model.model_dump(mode="json"))
        sim = prepare_volume(drawn)
        _rd.release_gpu_memory()
        for k, spec in enumerate(random_cuts(sim.solid, cuts, cut_rng, PROBE_RESOLUTION)):
            look = photo_looks[int(look_rng.integers(len(photo_looks)))]
            entry: dict[str, object] = {"draw": d, "cut": k, "settings": settings}
            entry["plane"] = [round(spec.tilt_deg, 2), round(spec.azimuth_deg, 2)]
            try:
                result = sim.cut(spec).result
            except ValueError as exc:
                out.append({**entry, "error": str(exc)})
                continue
            pixels = resolution_for(render_slab(result), result.domain.mask, look, resolution)
            if pixels != PROBE_RESOLUTION:
                result = sim.cut(spec.model_copy(update={"resolution": pixels})).result
            entry["resolution"] = pixels
            rgb = render_slab(result)
            mask = result.domain.mask
            quartz = result.fields.phase == Phase.QUARTZ
            entry.update(measure_cut(rgb, mask, quartz, look, measure_rng.spawn(1)[0]))
            out.append(entry)
        del sim
        _rd.release_gpu_memory()
    return out


def survey_models(
    names: list[str],
    photo_looks: list[Look],
    *,
    draws: int = DRAWS,
    cuts: int = CUTS,
    resolution: int = MAX_RESOLUTION,
    path: Path = CUT_SHAPES_PATH,
) -> dict[str, list[dict[str, object]]]:
    """Each preset's cuts, from the cache where it is current."""
    saved: dict[str, dict[str, Any]] = json.loads(path.read_text("utf-8")) if path.exists() else {}
    out: dict[str, list[dict[str, object]]] = {}
    for i, name in enumerate(names):
        progress.report(i / max(len(names), 1), f"cutting {name}")
        key = _key(load_volume_preset(name), draws, cuts, resolution, len(photo_looks))
        if saved.get(name, {}).get("key") == key:
            out[name] = saved[name]["cuts"]
            continue
        with progress.span(i / len(names), (i + 1) / len(names)):
            cut_entries = survey_preset(
                name, photo_looks, draws=draws, cuts=cuts, resolution=resolution
            )
        out[name] = cut_entries
        saved[name] = {"key": key, "cuts": cut_entries}
        _write(path, saved)
    return out


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", "utf-8")
    tmp.replace(path)


@dataclass(frozen=True)
class Comparison:
    """How one statistic of a model's cuts sits against the photos' 10-90% range."""

    n: int
    median: float
    below: float  # share of cuts under the photos' 10th percentile
    inside: float
    above: float
    setting: str | None  # the setting whose rank correlation with it is strongest
    rho: float | None


def _ranks(x: NDArray[np.float64]) -> NDArray[np.float64]:
    order = np.argsort(x, kind="stable")
    r = np.empty(x.size)
    r[order] = np.arange(x.size, dtype=np.float64)
    for v in np.unique(x):  # ties share their mean rank
        tied = x == v
        r[tied] = r[tied].mean()
    return r


def spearman(x: NDArray[np.float64], y: NDArray[np.float64]) -> float | None:
    """Spearman's rank correlation; None when either side doesn't vary."""
    rx, ry = _ranks(x), _ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


MIN_DRAWS = 8  # draws needed before a setting is named
# A setting is named only if its correlation is stronger than the strongest any
# setting reaches with the draws' results shuffled, in this share of shuffles: a
# model has 20-40 settings, so a fixed threshold would name some by chance.
SHUFFLES = 500
SHOWN_BEYOND_CHANCE = 0.95


def _draw_of(entry: dict[str, object]) -> int:
    d = entry.get("draw")
    return d if isinstance(d, int) else -1


def _strongest(
    rows: list[tuple[float, int, dict[str, float]]],
) -> tuple[str | None, float | None]:
    """The setting whose rank correlation with a statistic is strongest, over
    draws (each draw's cuts share its settings, so they count once, by their
    median), when there are enough draws and it beats chance: the strongest
    correlation over all settings with the results shuffled (`SHUFFLES` times,
    a fixed seed)."""
    by_draw: dict[int, tuple[list[float], dict[str, float]]] = {}
    for v, d, settings in rows:
        by_draw.setdefault(d, ([], settings))[0].append(v)
    if len(by_draw) < MIN_DRAWS:
        return None, None
    values = np.array([float(np.median(v)) for v, _ in by_draw.values()])
    draws = [s for _, s in by_draw.values()]
    names = sorted(set[str].intersection(*(set(s) for s in draws)))
    ranked = [_standard(_ranks(np.array([s[n] for s in draws], dtype=np.float64))) for n in names]
    varied = [(n, r) for n, r in zip(names, ranked, strict=True) if r is not None]
    y = _standard(_ranks(values))
    if not varied or y is None:
        return None, None
    # Spearman's rho for every setting at once: correlations of standardised ranks.
    matrix = np.stack([r for _, r in varied])
    rhos = matrix @ y / y.size
    best = int(np.argmax(np.abs(rhos)))
    rng = np.random.default_rng(0)
    shuffled = np.stack([rng.permutation(y) for _ in range(SHUFFLES)])
    chance = np.abs(matrix @ shuffled.T / y.size).max(axis=0)
    if abs(rhos[best]) <= float(np.quantile(chance, SHOWN_BEYOND_CHANCE)):
        return None, None
    return varied[best][0], float(rhos[best])


def _standard(x: NDArray[np.float64]) -> NDArray[np.float64] | None:
    sd = float(x.std())
    return None if sd == 0 else (x - x.mean()) / sd


def compare(
    cuts: list[dict[str, object]], photos: dict[str, Spread | None]
) -> dict[str, Comparison | None]:
    """Each statistic of a model's cuts that matched their photos, against the
    photos' spread."""
    out: dict[str, Comparison | None] = {}
    for stat in STATISTICS:
        rows = [
            (v, _draw_of(c), _settings(c))
            for c in cuts
            if c.get("matched") is True and (v := _number(c, stat)) is not None
        ]
        ref = photos.get(stat)
        if not rows or ref is None:
            out[stat] = None
            continue
        values = np.array([v for v, _, _ in rows])
        setting, rho = _strongest(rows)
        out[stat] = Comparison(
            n=len(rows),
            median=float(np.median(values)),
            below=float((values < ref.low).mean()),
            inside=float(((values >= ref.low) & (values <= ref.high)).mean()),
            above=float((values > ref.high).mean()),
            setting=setting,
            rho=rho,
        )
    return out
