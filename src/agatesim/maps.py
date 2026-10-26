"""Feature maps from image-level tags (ADR 0068).

The image model behind the form classifier also describes each 14 px square of
a photo (its patch features). A photo is read whole at 518 px on its long side,
so a 37-patch-wide grid. For each map feature, a logistic layer gives every
patch a score; it is trained by multiple-instance learning: a photo's score is
the mean of its top-scoring patches, fitted to whether the photo is tagged with
the feature. No pixel is ever labelled for training.

The maps are tested only on the owner's taps on held-out photos
(agatesim.taps): how well each map ranks inside points above outside points,
against chance and against a centre prior. A map is shown only if it beats
both. Maps describe appearance, never how a feature formed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim import progress
from agatesim.classify import MEAN, MODEL_PATH, MODEL_SHA256, MODELS_DIR, STD, specimen_group
from agatesim.library import Label, LibraryImage, load_labels, load_library
from agatesim.taps import (
    MAP_GROUPS,
    TRAIN_TAPS_TOML,
    FeatureTaps,
    Taps,
    load_taps,
    targets,
)

MAPS_PATH = MODELS_DIR / "maps.npz"
PATCH_PX = 14
LONG_PATCHES = 37  # 518 px on the long side

# Training choices (effective: tuned to the data, not physical).
DIMS = 64  # patch features are reduced to this many principal components
TOP_SHARE = 0.1  # a photo's score is the mean of its top 10% of patches
REGULARISATION = 1.0  # L2 strength on the weights
BALANCE = 0.5  # rare features' photos weighted up, as in the classifier
MIN_TRAIN = 8  # tagged training photos a feature needs to get a map

# Testing (ADR 0068 section 2).
MIN_TEST = 5  # tapped test photos a feature needs to be judged
BOOTSTRAP = 2000
CONFIDENCE = 0.95


class PatchEmbedder(Protocol):
    """Turns an RGB photo into a (rows, cols, dims) grid of patch features."""

    key: str

    def patches(self, rgb: NDArray[np.uint8]) -> NDArray[np.float32]: ...


def grid_shape(width: int, height: int, long_patches: int = LONG_PATCHES) -> tuple[int, int]:
    """(rows, cols) of patches for a photo read whole: the long side gets
    `long_patches`, the short side keeps the aspect to within half a patch."""
    if width >= height:
        return max(1, round(long_patches * height / width)), long_patches
    return long_patches, max(1, round(long_patches * width / height))


def prepare_whole(rgb: NDArray[np.uint8]) -> NDArray[np.float32]:
    """A whole photo as the model expects it, no crop: 1 x 3 x (14 rows) x (14 cols)."""
    h, w = rgb.shape[:2]
    rows, cols = grid_shape(w, h)
    im = (
        Image.fromarray(rgb)
        .convert("RGB")
        .resize((cols * PATCH_PX, rows * PATCH_PX), Image.Resampling.BICUBIC)
    )
    a = (np.asarray(im, np.float32) / 255.0 - MEAN) / STD
    return a.transpose(2, 0, 1)[None].astype(np.float32)


class OnnxPatchEmbedder:
    """DINOv2-small's patch tokens (384 numbers per patch)."""

    key = f"dinov2-small-{MODEL_SHA256[:8]}-whole{LONG_PATCHES}"

    def __init__(self, path: Path = MODEL_PATH) -> None:
        from agatesim._onnx import Session

        if not path.exists():
            raise FileNotFoundError(f"no model file at {path}: run `agatesim classify fetch`")
        self._session = Session(path)

    def patches(self, rgb: NDArray[np.uint8]) -> NDArray[np.float32]:
        x = prepare_whole(rgb)
        rows, cols = x.shape[2] // PATCH_PX, x.shape[3] // PATCH_PX
        h = self._session.run(x)[0]
        return h[1:].reshape(rows, cols, -1)


class PatchCache:
    """Patch features on disk, one float16 file per photo (about 1 MB each),
    so a training run never holds all of them at full size."""

    def __init__(self, embedder: PatchEmbedder, directory: Path = MODELS_DIR) -> None:
        self.embedder = embedder
        self.directory = directory / f"patches-{embedder.key}"

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.npy"

    def __contains__(self, key: str) -> bool:
        return self._path(key).exists()

    def get(self, key: str, rgb: Callable[[], NDArray[np.uint8]]) -> NDArray[np.float32]:
        path = self._path(key)
        if path.exists():
            return np.load(path).astype(np.float32)
        p = self.embedder.patches(rgb()).astype(np.float32)
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.stem + ".part.npy")
        np.save(tmp, p.astype(np.float16))
        tmp.replace(path)
        return p


def _library_key(image: LibraryImage) -> str:
    return f"{image.id}-{image.path.stat().st_size}"


def library_patches(cache: PatchCache, image: LibraryImage) -> NDArray[np.float32]:
    from agatesim.specimen.photo import load_photo

    return cache.get(_library_key(image), lambda: load_photo(image.path.read_bytes(), 1024).rgb)


# --- training -------------------------------------------------------------------


@dataclass(frozen=True)
class Bag:
    """One training photo: its patch features (patches x dims, float16 to halve
    the memory), the maps it is tagged for, any training taps as (map, patch
    index, 1 inside or 0 outside) (ADR 0070), and the maps it sits out because
    its tag is unsure (ADR 0071)."""

    key: str
    patches: NDArray[np.float16]
    tags: frozenset[str]
    points: tuple[tuple[str, int, float], ...] = ()
    unsure: frozenset[str] = frozenset()


def patch_index(rows: int, cols: int, x: float, y: float) -> int:
    """The flat index of the patch under (x, y), fractions of the photo."""
    return min(int(y * rows), rows - 1) * cols + min(int(x * cols), cols - 1)


def map_of(tag: str) -> str | None:
    """The map a tag feeds, if any (ADR 0071)."""
    return next((m for m, tags in MAP_GROUPS.items() if tag in tags), None)


def map_tags(label: Label) -> tuple[frozenset[str], frozenset[str]]:
    """The maps a photo is tagged for, and those it sits out: a map whose only
    tags on the photo are unsure is neither yes nor no (ADR 0071)."""
    tagged = frozenset(m for t in targets(label) if (m := map_of(t)))
    unsure = frozenset(m for t in label.unsure if (m := map_of(t))) - tagged
    return tagged, unsure


def merged(
    taps: dict[str, FeatureTaps], tags: Iterable[str] | None = None
) -> dict[str, FeatureTaps]:
    """Taps by map: a map's taps are its tags' taps together. With `tags`,
    only taps on those tags count."""
    out: dict[str, FeatureTaps] = {}
    for t, ft in sorted(taps.items()):
        m = map_of(t)
        if m is None or (tags is not None and t not in tags):
            continue
        old = out.get(m, FeatureTaps())
        out[m] = FeatureTaps(inside=old.inside + ft.inside, outside=old.outside + ft.outside)
    return out


def tap_points(
    rows: int, cols: int, taps: dict[str, FeatureTaps]
) -> tuple[tuple[str, int, float], ...]:
    return tuple(
        (f, patch_index(rows, cols, x, y), target)
        for f, t in sorted(taps.items())
        for pts, target in ((t.inside, 1.0), (t.outside, 0.0))
        for x, y in pts
    )


@dataclass(frozen=True)
class FeatureMaps:
    """Per-patch scores for each feature: patch features are centred, projected
    onto `components` and scaled, then each feature's logistic layer applies."""

    features: tuple[str, ...]
    mean: NDArray[np.float32]  # (dims,)
    components: NDArray[np.float32]  # (dims, DIMS), scaled to unit variance
    weights: NDArray[np.float64]  # (features, DIMS)
    bias: NDArray[np.float64]  # (features,)
    embedder_key: str
    counts: tuple[int, ...]  # tagged training photos per map
    tested: tuple[Score, ...] = ()  # scores on the test taps, from `build`

    @property
    def shown(self) -> tuple[str, ...]:
        """Features whose map beat chance and the centre prior on the taps."""
        return tuple(s.feature for s in self.tested if s.passes)

    def reduce(self, patches: NDArray[np.float32]) -> NDArray[np.float32]:
        flat = patches.reshape(-1, patches.shape[-1])
        return ((flat - self.mean) @ self.components).astype(np.float32)

    def scores(self, patches: NDArray[np.float32]) -> dict[str, NDArray[np.float64]]:
        """Each feature's probability per patch, as a (rows, cols) grid."""
        rows, cols = patches.shape[:2]
        z = self.reduce(patches).astype(np.float64) @ self.weights.T + self.bias
        p = 1.0 / (1.0 + np.exp(-z))
        return {f: p[:, i].reshape(rows, cols) for i, f in enumerate(self.features)}

    def save(self, path: Path = MAPS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path,
            mean=self.mean,
            components=self.components,
            weights=self.weights,
            bias=self.bias,
            meta=np.array(
                json.dumps(
                    {
                        "features": self.features,
                        "key": self.embedder_key,
                        "counts": self.counts,
                        "tested": [asdict(t) for t in self.tested],
                    }
                )
            ),
        )

    @classmethod
    def load(cls, path: Path = MAPS_PATH) -> FeatureMaps:
        with np.load(path) as z:
            meta = json.loads(str(z["meta"]))
            return cls(
                tuple(meta["features"]),
                z["mean"],
                z["components"],
                z["weights"],
                z["bias"],
                meta["key"],
                tuple(meta["counts"]),
                tuple(Score(**t) for t in meta.get("tested", [])),
            )


def _projection(
    bags: Sequence[Bag], dims: int, sample: int = 200
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Mean and whitened principal components of the patch features, from up
    to `sample` patches per photo (fixed draws)."""
    rng = np.random.default_rng(0)
    rows = [
        b.patches[rng.choice(len(b.patches), min(sample, len(b.patches)), replace=False)]
        for b in bags
    ]
    x = np.concatenate(rows).astype(np.float64)  # float16 rows widened once
    mean = x.mean(axis=0)
    _, s, vt = np.linalg.svd(x - mean, full_matrices=False)
    k = min(dims, vt.shape[0])
    scale = s[:k] / np.sqrt(max(len(x) - 1, 1))
    components = vt[:k].T / np.maximum(scale, 1e-9)
    return mean.astype(np.float32), components.astype(np.float32)


def _top(n: int, share: float = TOP_SHARE) -> int:
    return max(1, round(n * share))


def _fit_one(
    xs: Sequence[NDArray[np.float32]],
    y: NDArray[np.float64],
    points: Sequence[tuple[int, int, float]] = (),
) -> tuple[NDArray[np.float64], float]:
    """Multiple-instance logistic regression: a photo's score is the mean of
    its top patches' scores; L2 on the weights, rare positives weighted up.
    Tapped patches (photo, patch, 1 or 0) add a logistic term on the patch's
    own score; all points together weigh as much as all tags (ADR 0070)."""
    from agatesim._scipy import minimize_lbfgs

    pos, neg = float(y.sum()), float((1 - y).sum())
    if pos == 0 or neg == 0:
        return np.zeros(xs[0].shape[1]), (20.0 if neg == 0 else -20.0)
    sw = np.where(y > 0, (neg / pos) ** BALANCE, 1.0)
    sw = sw / sw.sum()
    lam = REGULARISATION / len(y)
    ks = [_top(len(x)) for x in xs]
    px: NDArray[np.float64] = np.array([xs[i][j] for i, j, _ in points], np.float64).reshape(
        len(points), xs[0].shape[1]
    )
    pt: NDArray[np.float64] = np.array([t for _, _, t in points], np.float64)

    def loss(theta: NDArray[np.float64]) -> tuple[float, NDArray[np.float64]]:
        beta, b = theta[:-1], theta[-1]
        total = 0.5 * lam * float(beta @ beta)
        grad = np.concatenate([lam * beta, [0.0]])
        for x, k, yi, wi in zip(xs, ks, y, sw, strict=True):
            z = x @ beta.astype(np.float32)
            idx = np.argpartition(z, len(z) - k)[-k:]
            s = float(z[idx].mean()) + b
            total += wi * (float(np.logaddexp(0.0, s)) - yi * s)
            g = wi * (1.0 / (1.0 + np.exp(-s)) - yi)
            grad[:-1] += g * x[idx].mean(axis=0)
            grad[-1] += g
        if len(pt):
            s: NDArray[np.float64] = px @ beta + b
            total += float(np.mean(np.logaddexp(0.0, s) - pt * s))
            g = (1.0 / (1.0 + np.exp(-s)) - pt) / len(pt)
            grad[:-1] += px.T @ g
            grad[-1] += float(g.sum())
        return total, grad

    # Start from the difference of tagged and untagged photos' mean patches: at
    # zero every patch ties, the top patches are arbitrary and the fit stalls.
    means = np.stack([x.mean(axis=0) for x in xs]).astype(np.float64)
    start = means[y > 0].mean(axis=0) - means[y == 0].mean(axis=0)
    start /= max(float(np.linalg.norm(start)), 1e-12)
    theta = minimize_lbfgs(loss, np.concatenate([start, [0.0]]))
    return theta[:-1], float(theta[-1])


def train(
    bags: Sequence[Bag], features: Sequence[str], embedder_key: str, dims: int = DIMS
) -> FeatureMaps:
    mean, components = _projection(bags, dims)
    xs = [((b.patches.astype(np.float32) - mean) @ components).astype(np.float32) for b in bags]
    counts = tuple(sum(f in b.tags for b in bags) for f in features)
    kept = [f for f, n in zip(features, counts, strict=True) if n >= MIN_TRAIN]
    weights: list[NDArray[np.float64]] = []
    bias: list[float] = []
    for n, f in enumerate(kept):
        progress.report(n / len(kept), f"training the {f} map")
        use = [i for i, bag in enumerate(bags) if f not in bag.unsure]
        points = [(u, j, t) for u, i in enumerate(use) for g, j, t in bags[i].points if g == f]
        y = np.array([f in bags[i].tags for i in use], np.float64)
        beta, b = _fit_one([xs[i] for i in use], y, points)
        weights.append(beta)
        bias.append(b)
    return FeatureMaps(
        tuple(kept),
        mean,
        components,
        np.stack(weights) if weights else np.zeros((0, components.shape[1])),
        np.array(bias),
        embedder_key,
        tuple(n for n in counts if n >= MIN_TRAIN),
    )


def training_ids(labels: dict[str, Label], held: Taps) -> list[str]:
    """Usable labelled photos, leaving out the held-out ones and every photo
    that probably shows the same specimen as one of them."""
    test_groups = {specimen_group(k) for k in held.photos}
    return sorted(
        k
        for k, v in labels.items()
        if v.verdict == "forms" and specimen_group(k) not in test_groups
    )


def library_bags(
    cache: PatchCache,
    ids: Iterable[str],
    labels: dict[str, Label],
    taps: dict[str, dict[str, FeatureTaps]] | None = None,
) -> list[Bag]:
    """Training bags; `taps` are training taps by photo (ADR 0070)."""
    taps = taps or {}
    images = {i.id: i for i in load_library().images}
    todo = [k for k in ids if k in images and images[k].path.exists()]
    out: list[Bag] = []
    for n, k in enumerate(todo):
        progress.report(n / max(len(todo), 1), f"reading {images[k].title}")
        p = library_patches(cache, images[k])
        flat = p.reshape(-1, p.shape[-1]).astype(np.float16)
        tagged, unsure = map_tags(labels[k])
        mine = merged(taps.get(k, {}), targets(labels[k]))
        out.append(Bag(k, flat, tagged, tap_points(p.shape[0], p.shape[1], mine), unsure))
    return out


def build(cache: PatchCache | None = None, path: Path = MAPS_PATH) -> FeatureMaps:
    """Train the maps on the library's usable photos minus the held-out ones,
    with the training taps, score them on the test taps, and save both."""
    cache = cache or PatchCache(OnnxPatchEmbedder())
    labels = load_labels()
    train_taps = load_taps(TRAIN_TAPS_TOML, "train").taps
    bags = library_bags(cache, training_ids(labels, load_taps()), labels, train_taps)
    maps = train(bags, tuple(MAP_GROUPS), cache.embedder.key)
    maps = replace(maps, tested=tuple(evaluate(maps, cache)))
    maps.save(path)
    return maps


# --- testing against taps -------------------------------------------------------


def value_at(grid: NDArray[np.float64], x: float, y: float) -> float:
    """A patch grid read at (x, y), fractions of the photo: bilinear between
    patch centres, held flat beyond the outer centres."""
    rows, cols = grid.shape
    gx = min(max(x * cols - 0.5, 0.0), cols - 1.0)
    gy = min(max(y * rows - 0.5, 0.0), rows - 1.0)
    x0, y0 = int(gx), int(gy)
    x1, y1 = min(x0 + 1, cols - 1), min(y0 + 1, rows - 1)
    fx, fy = gx - x0, gy - y0
    top = grid[y0, x0] * (1 - fx) + grid[y0, x1] * fx
    bottom = grid[y1, x0] * (1 - fx) + grid[y1, x1] * fx
    return float(top * (1 - fy) + bottom * fy)


def centre_prior(x: float, y: float, aspect: float) -> float:
    """The shortcut baseline: higher nearer the photo's middle (`aspect` is
    height / width, so distances are in photo units)."""
    return -float(np.hypot(x - 0.5, (y - 0.5) * aspect))


def ranking(inside: Sequence[float], outside: Sequence[float]) -> float:
    """The chance that an inside point outranks an outside one (ties count
    half): the area under the ROC curve. 0.5 is chance."""
    a = np.asarray(inside, np.float64)[:, None]
    b = np.asarray(outside, np.float64)[None, :]
    return float(((a > b).sum() + 0.5 * (a == b).sum()) / (a.size * b.size))


@dataclass(frozen=True)
class Score:
    feature: str
    photos: int  # tapped test photos with inside and outside points
    map: float  # mean per-photo ranking score of the map
    centre: float  # the same for the centre prior
    low_vs_chance: float  # lower confidence bound of map - 0.5
    low_vs_centre: float  # lower confidence bound of map - centre
    passes: bool


def score(feature: str, per_photo: Sequence[tuple[float, float]], seed: int = 0) -> Score:
    """Judge one feature from (map, centre) ranking scores per test photo: a
    paired bootstrap over photos must put both gains above zero."""
    n = len(per_photo)
    if n == 0:
        return Score(feature, 0, float("nan"), float("nan"), float("nan"), float("nan"), False)
    m = np.array([p[0] for p in per_photo])
    c = np.array([p[1] for p in per_photo])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, (BOOTSTRAP, n))
    q = (1 - CONFIDENCE) / 2
    low_chance = float(np.quantile(m[idx].mean(axis=1) - 0.5, q))
    low_centre = float(np.quantile((m[idx] - c[idx]).mean(axis=1), q))
    passes = n >= MIN_TEST and low_chance > 0 and low_centre > 0
    return Score(feature, n, float(m.mean()), float(c.mean()), low_chance, low_centre, passes)


def photo_rankings(
    grid: NDArray[np.float64], taps: FeatureTaps, aspect: float
) -> tuple[float, float] | None:
    """(map, centre prior) ranking scores on one photo, or None without both kinds of point."""
    if not taps.inside or not taps.outside:
        return None
    mi = [value_at(grid, x, y) for x, y in taps.inside]
    mo = [value_at(grid, x, y) for x, y in taps.outside]
    ci = [centre_prior(x, y, aspect) for x, y in taps.inside]
    co = [centre_prior(x, y, aspect) for x, y in taps.outside]
    return ranking(mi, mo), ranking(ci, co)


def evaluate(maps: FeatureMaps, cache: PatchCache | None = None) -> list[Score]:
    """Score every map on the owner's taps on the held-out photos (a map's
    taps are those on all its tags)."""
    cache = cache or PatchCache(OnnxPatchEmbedder())
    held = load_taps()
    images = {i.id: i for i in load_library().images}
    per: dict[str, list[tuple[float, float]]] = {f: [] for f in maps.features}
    for n, k in enumerate(held.photos):
        progress.report(n / len(held.photos), "scoring the maps on the test taps")
        taps = merged(held.taps.get(k, {}))
        if not any(f in taps for f in maps.features) or not images[k].path.exists():
            continue
        p = library_patches(cache, images[k])
        grids = maps.scores(p)
        aspect = p.shape[0] / p.shape[1]
        for f in maps.features:
            r = photo_rankings(grids[f], taps[f], aspect) if f in taps else None
            if r is not None:
                per[f].append(r)
    return [score(f, per[f]) for f in maps.features]
