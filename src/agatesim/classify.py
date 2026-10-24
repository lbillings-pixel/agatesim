"""A learned form classifier (ADR 0063 section 3, ADR 0067).

A pretrained image model (DINOv2-small, run locally through ONNX Runtime) turns
a photo into an embedding; a small classifier on top, one logistic regression
per form, says how likely each form is. It is trained on the labelled reference
library and on rendered simulations, which are free labelled examples of each
form's appearance. Several forms can be likely at once, and when none is, the
answer is "undetermined".

The model file is fetched on demand into references/models/ (gitignored) and
checked against a pinned hash. A form classifier recognises appearance: it is
never evidence for a formation mechanism, whatever it was trained on.
"""

from __future__ import annotations

import hashlib
import re
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim import progress
from agatesim.library import AGENT, ROOT, Label, load_labels, load_library

if TYPE_CHECKING:
    from agatesim.config import RunConfig

MODELS_DIR = ROOT / "references" / "models"
MODEL_URL = (
    "https://huggingface.co/onnx-community/dinov2-small/resolve/"
    "8b1f705a3a7f6f062f6bdd21986c1583d3ef105d/onnx/model.onnx"
)
MODEL_SHA256 = "f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a"
MODEL_PATH = MODELS_DIR / "dinov2-small.onnx"
CLASSIFIER_PATH = MODELS_DIR / "classifier.npz"

# The model's own preparation (its preprocessor_config.json): shortest side to
# 256 px, bicubic, centre crop to 224 px, ImageNet mean and spread.
RESIZE_PX = 256
CROP_PX = 224
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

LIKELY = 0.5  # a form is reported when its probability reaches this
SIM_RESOLUTION = 320  # simulated slabs: the model sees 224 px anyway
SIM_VARIANTS = 30  # simulated slabs per form
SIM_WEIGHT = 0.1  # a simulated slab counts this much against one real photo
SIM_VERSION = 1  # bump when the simulated training set changes


class Embedder(Protocol):
    """Turns RGB photos (H x W x 3, uint8) into unit-length embeddings."""

    key: str  # names the embedding space, for caches

    def embed(self, rgb: NDArray[np.uint8]) -> NDArray[np.float32]: ...


def prepare(rgb: NDArray[np.uint8]) -> NDArray[np.float32]:
    """A photo as the model expects it: 1 x 3 x 224 x 224, normalised."""
    im = Image.fromarray(rgb).convert("RGB")
    w, h = im.size
    s = RESIZE_PX / min(w, h)
    im = im.resize(
        (max(CROP_PX, round(w * s)), max(CROP_PX, round(h * s))), Image.Resampling.BICUBIC
    )
    w, h = im.size
    left, top = (w - CROP_PX) // 2, (h - CROP_PX) // 2
    crop = im.crop((left, top, left + CROP_PX, top + CROP_PX))
    a = (np.asarray(crop, np.float32) / 255.0 - MEAN) / STD
    return a.transpose(2, 0, 1)[None].astype(np.float32)


def _unit(v: NDArray[np.float32]) -> NDArray[np.float32]:
    return (v / max(float(np.linalg.norm(v)), 1e-12)).astype(np.float32)


class OnnxEmbedder:
    """DINOv2-small on the processor: the class token and the mean of the patch
    tokens, side by side (768 numbers)."""

    key = f"dinov2-small-{MODEL_SHA256[:8]}"

    def __init__(self, path: Path = MODEL_PATH) -> None:
        from agatesim._onnx import Session

        if not path.exists():
            raise FileNotFoundError(f"no model file at {path}: run `agatesim classify fetch`")
        self._session = Session(path)

    def embed(self, rgb: NDArray[np.uint8]) -> NDArray[np.float32]:
        h = self._session.run(prepare(rgb))[0]
        return _unit(np.concatenate([h[0], h[1:].mean(axis=0)]).astype(np.float32))


def fetch_model(url: str = MODEL_URL, sha256: str = MODEL_SHA256, path: Path = MODEL_PATH) -> bool:
    """Download the model file once, checked against its pinned hash. Returns
    whether it was downloaded (False: already there)."""
    if path.exists() and _sha256(path) == sha256:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    progress.report(None, "fetching the image model (84 MB)")
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=600) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("the downloaded model file does not match its pinned hash")
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return True


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --- training examples ---------------------------------------------------------


@dataclass(frozen=True)
class Example:
    """One training photo: its embedding, its forms, how much it counts, and a
    group (crops and copies of one specimen share a group, so a test never
    sees a near-copy of a training photo)."""

    key: str
    embedding: NDArray[np.float32]
    forms: frozenset[str]
    weight: float
    group: str
    simulated: bool


class EmbeddingCache:
    """Embeddings on disk, keyed by what they were made from."""

    def __init__(self, embedder: Embedder, directory: Path = MODELS_DIR) -> None:
        self.embedder = embedder
        self.path = directory / f"embeddings-{embedder.key}.npz"
        self._data: dict[str, NDArray[np.float32]] = {}
        if self.path.exists():
            with np.load(self.path) as z:
                self._data = {k: z[k] for k in z.files}
        self._dirty = False

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str, rgb: Callable[[], NDArray[np.uint8]]) -> NDArray[np.float32]:
        if key not in self._data:
            self._data[key] = self.embedder.embed(rgb())
            self._dirty = True
        return self._data[key]

    def save(self) -> None:
        if self._dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.stem + ".part.npz")
            np.savez(tmp, **self._data)  # pyright: ignore[reportArgumentType]
            tmp.replace(self.path)
            self._dirty = False


def specimen_group(image_id: str) -> str:
    """Photo ids that probably show one specimen share a group: crops, details
    and numbered copies ("detail-x-cropped", "x-2")."""
    g = re.sub(r"^(detail|crop|closeup|close-up)-", "", image_id)
    g = re.sub(r"-(cropped|crop|detail|edit|edited)$", "", g)
    return re.sub(r"-\d{1,2}$", "", g)


def library_examples(
    cache: EmbeddingCache, labels: dict[str, Label] | None = None
) -> list[Example]:
    """The labelled reference photos that show forms."""
    from agatesim.specimen.photo import load_photo

    labels = load_labels() if labels is None else labels
    out: list[Example] = []
    todo = [i for i in load_library().images if i.id in labels and labels[i.id].verdict == "forms"]
    for n, image in enumerate(todo):
        progress.report(n / max(len(todo), 1), f"reading {image.title}")
        if not image.path.exists():
            continue
        key = f"lib/{image.id}/{image.path.stat().st_size}"
        e = cache.get(key, lambda p=image.path: load_photo(p.read_bytes(), 1024).rgb)
        out.append(
            Example(key, e, frozenset(labels[image.id].forms), 1.0, specimen_group(image.id), False)
        )
    return out


# The owner's own photos are labelled apart from the library (ADR 0066): one
# label beside each photo in the specimens folder, never in the repository.
OWN_LABEL_SUFFIX = ".label.json"


def own_label_path(folder: Path, name: str) -> Path:
    return folder / ".agatesim" / f"{name}{OWN_LABEL_SUFFIX}"


def own_labels(folder: Path) -> dict[str, Label]:
    """The owner's labels of their own photos, by photo name."""
    side = folder / ".agatesim"
    if not side.is_dir():
        return {}
    out: dict[str, Label] = {}
    for p in sorted(side.glob(f"*{OWN_LABEL_SUFFIX}")):
        name = p.name[: -len(OWN_LABEL_SUFFIX)]
        if (folder / name).is_file():
            out[name] = Label.model_validate_json(p.read_text("utf-8"))
    return out


def _own_key(path: Path) -> str:
    st = path.stat()
    return f"own/{path.name}/{st.st_size}/{st.st_mtime_ns}"


def own_examples(cache: EmbeddingCache, folder: Path) -> list[Example]:
    """The owner's photos they have labelled with forms. Each is its own group:
    photos of one specimen can't be told apart by name here."""
    from agatesim.specimen.photo import load_photo

    todo = [(n, lab) for n, lab in own_labels(folder).items() if lab.verdict == "forms"]
    out: list[Example] = []
    for n, (name, label) in enumerate(todo):
        progress.report(n / max(len(todo), 1), f"reading {name}")
        path = folder / name
        key = _own_key(path)
        e = cache.get(key, lambda p=path: load_photo(p.read_bytes(), 1024).rgb)
        out.append(Example(key, e, frozenset(label.forms), 1.0, f"own/{name}", False))
    return out


def missing_embeddings(cache: EmbeddingCache, specimens: Path | None = None) -> tuple[int, int]:
    """Photos and simulated slabs that training would still have to embed."""
    labels = load_labels()
    photos = sum(
        1
        for i in load_library().images
        if i.id in labels
        and labels[i.id].verdict == "forms"
        and i.path.exists()
        and f"lib/{i.id}/{i.path.stat().st_size}" not in cache
    )
    if specimens is not None:
        photos += sum(
            1
            for name, lab in own_labels(specimens).items()
            if lab.verdict == "forms" and _own_key(specimens / name) not in cache
        )
    sims = sum(
        1
        for form in trainable_forms()
        for v in range(SIM_VARIANTS)
        if f"sim{SIM_VERSION}/{form}/{v}" not in cache
    )
    return photos, sims


def _render_sim(config: RunConfig, seed: int) -> NDArray[np.uint8]:
    """One simulated slab, varied; optical forms are shown as they are seen
    (as in the gallery)."""
    from agatesim import optics
    from agatesim.render import render_slab
    from agatesim.simulate import simulate

    result = simulate(config.model_copy(update={"seed": seed}))
    if config.archetype == "shadow":
        rgb = optics.render_shadow(result, 30.0)
    elif config.archetype == "iris":
        rgb = optics.render_iris(result, 18.0)
    else:
        rgb = render_slab(result)
    return _vary(rgb, np.random.default_rng([SIM_VERSION, seed]))


def _vary(rgb: NDArray[np.uint8], rng: np.random.Generator) -> NDArray[np.uint8]:
    """Turns, flips and colour: real agates come in every orientation and many
    colours, simulations in one of each."""
    a = np.rot90(rgb, int(rng.integers(4)))
    if rng.random() < 0.5:
        a = a[:, ::-1]
    f = a.astype(np.float32)
    if rng.random() < 0.25:
        f = np.repeat(f.mean(axis=2, keepdims=True), 3, axis=2)
    else:
        f = f[..., rng.permutation(3)] * rng.uniform(0.75, 1.25, 3)
    f = (f - f.mean()) * rng.uniform(0.8, 1.2) + f.mean() * rng.uniform(0.85, 1.15)
    return np.clip(f, 0, 255).astype(np.uint8)


def simulated_examples(
    cache: EmbeddingCache, forms: Iterable[str], variants: int = SIM_VARIANTS
) -> list[Example]:
    """Rendered slabs of each form's procedural preset, one seed per variant."""
    from agatesim.config import load_preset

    forms = list(forms)
    out: list[Example] = []
    for i, form in enumerate(forms):
        base = load_preset(form).with_resolution(SIM_RESOLUTION)
        for v in range(variants):
            progress.report((i * variants + v) / (len(forms) * variants), f"simulating {form}")
            key = f"sim{SIM_VERSION}/{form}/{v}"
            e = cache.get(key, lambda b=base, s=v: _render_sim(b, s))
            out.append(Example(key, e, frozenset({form}), SIM_WEIGHT, key, True))
    return out


# --- the classifier --------------------------------------------------------------


@dataclass(frozen=True)
class Classifier:
    """One logistic regression per form on unit embeddings."""

    forms: tuple[str, ...]
    weights: NDArray[np.float64]  # forms x dims
    bias: NDArray[np.float64]  # forms
    embedder_key: str
    real_counts: tuple[int, ...]  # labelled photos per form it was trained on

    def probabilities(self, embedding: NDArray[np.float32]) -> dict[str, float]:
        z = self.weights @ embedding.astype(np.float64) + self.bias
        p = 1.0 / (1.0 + np.exp(-z))
        return {f: float(q) for f, q in zip(self.forms, p, strict=True)}

    def save(self, path: Path = CLASSIFIER_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path,
            forms=np.array(self.forms),
            weights=self.weights,
            bias=self.bias,
            embedder_key=np.array(self.embedder_key),
            real_counts=np.array(self.real_counts),
        )

    @classmethod
    def load(cls, path: Path = CLASSIFIER_PATH) -> Classifier:
        with np.load(path) as z:
            return cls(
                tuple(str(f) for f in z["forms"]),
                z["weights"],
                z["bias"],
                str(z["embedder_key"]),
                tuple(int(n) for n in z["real_counts"]),
            )


REGULARISATION = 0.1  # L2 strength on the weights, per unit of training weight
BALANCE = 0.5  # 0: forms weighted as they come; 1: a form's photos count as much as the rest


def _fit_one(
    x: NDArray[np.float64], y: NDArray[np.float64], w: NDArray[np.float64]
) -> tuple[NDArray[np.float64], float]:
    """Weighted logistic regression with an L2 penalty; rare forms weighted up
    by BALANCE."""
    from agatesim._scipy import minimize_lbfgs

    pos = float((w * y).sum())
    neg = float((w * (1 - y)).sum())
    if pos == 0 or neg == 0:
        return np.zeros(x.shape[1]), (20.0 if neg == 0 else -20.0)
    up = (neg / pos) ** BALANCE
    sw = w * np.where(y > 0, up, 1.0)
    sw = sw / sw.sum()
    lam = REGULARISATION / float(w.sum())

    def loss(theta: NDArray[np.float64]) -> tuple[float, NDArray[np.float64]]:
        beta, b = theta[:-1], theta[-1]
        z = x @ beta + b
        p = 1.0 / (1.0 + np.exp(-z))
        # log(1 + e^z) - y z, computed stably
        ll = np.logaddexp(0.0, z) - y * z
        g = sw * (p - y)
        return (
            float(sw @ ll + 0.5 * lam * beta @ beta),
            np.concatenate([x.T @ g + lam * beta, [g.sum()]]),
        )

    theta = minimize_lbfgs(loss, np.zeros(x.shape[1] + 1))
    return theta[:-1], float(theta[-1])


def train(examples: Sequence[Example], forms: Sequence[str], embedder_key: str) -> Classifier:
    x = np.stack([e.embedding for e in examples]).astype(np.float64)
    w = np.array([e.weight for e in examples])
    weights: list[NDArray[np.float64]] = []
    bias: list[float] = []
    for form in forms:
        y = np.array([form in e.forms for e in examples], np.float64)
        beta, b = _fit_one(x, y, w)
        weights.append(beta)
        bias.append(b)
    counts = tuple(sum(form in e.forms for e in examples if not e.simulated) for form in forms)
    return Classifier(tuple(forms), np.stack(weights), np.array(bias), embedder_key, counts)


@dataclass(frozen=True)
class Answer:
    """Forms whose probability reaches LIKELY, most likely first; empty means
    undetermined. `ranked` keeps every form's probability for display."""

    likely: tuple[tuple[str, float], ...]
    ranked: tuple[tuple[str, float], ...]

    @property
    def undetermined(self) -> bool:
        return not self.likely


def answer(classifier: Classifier, embedding: NDArray[np.float32]) -> Answer:
    ranked = sorted(classifier.probabilities(embedding).items(), key=lambda kv: -kv[1])
    return Answer(tuple((f, p) for f, p in ranked if p >= LIKELY), tuple(ranked))


# --- evaluation ------------------------------------------------------------------


@dataclass(frozen=True)
class FormScore:
    form: str
    photos: int  # labelled photos showing it
    reported: int  # how many photos it reported it on
    correct: int  # of those, how many were right (found, of `photos`)


@dataclass(frozen=True)
class Evaluation:
    photos: int
    top_hit: float  # the most likely form is one of the photo's labels
    undetermined: float  # share of photos answered "undetermined"
    all_right: float  # at least one form reported, and every reported form is right
    forms: tuple[FormScore, ...]


def cross_validate(
    real: Sequence[Example],
    simulated: Sequence[Example],
    forms: Sequence[str],
    *,
    folds: int = 5,
    seed: int = 0,
) -> Evaluation:
    """Held-out results on the labelled photos: each fold's photos are judged
    by a classifier trained without them (or any photo of their specimen)."""
    groups = sorted({e.group for e in real})
    order = np.random.default_rng(seed).permutation(len(groups))
    fold_of = {groups[int(g)]: i % folds for i, g in enumerate(order)}
    answers: list[tuple[Example, Answer]] = []
    for k in range(folds):
        progress.report(k / folds, f"cross-validation fold {k + 1} of {folds}")
        test = [e for e in real if fold_of[e.group] == k]
        if not test:
            continue
        model = train([e for e in real if fold_of[e.group] != k] + list(simulated), forms, "")
        answers += [(e, answer(model, e.embedding)) for e in test]
    n = len(answers)
    scores: list[FormScore] = []
    for form in forms:
        truth = [form in e.forms for e, _ in answers]
        said = [any(f == form for f, _ in a.likely) for _, a in answers]
        hits = sum(t and s for t, s in zip(truth, said, strict=True))
        scores.append(FormScore(form, sum(truth), sum(said), hits))
    return Evaluation(
        n,
        sum(a.ranked[0][0] in e.forms for e, a in answers) / max(n, 1),
        sum(a.undetermined for _, a in answers) / max(n, 1),
        sum(bool(a.likely) and all(f in e.forms for f, _ in a.likely) for e, a in answers)
        / max(n, 1),
        tuple(scores),
    )


def gather(
    embedder: Embedder, specimens: Path | None = None, cache: EmbeddingCache | None = None
) -> tuple[list[Example], list[Example], list[str]]:
    """The labelled photos (the library's, and the owner's own when `specimens`
    is given), the simulated slabs and the forms to train on."""
    cache = EmbeddingCache(embedder) if cache is None else cache
    forms = trainable_forms()
    with progress.span(0.0, 0.2, "reading the labelled photos"):
        real = library_examples(cache)
        if specimens is not None:
            real += own_examples(cache, specimens)
    with progress.span(0.2, 1.0, "simulating slabs"):
        sims = simulated_examples(cache, forms)
    cache.save()
    return real, sims, forms


def trainable_forms() -> list[str]:
    """Every form in the archetype ladder that has a procedural preset."""
    from agatesim.archetypes.registry import load_registry
    from agatesim.config import load_preset

    out: list[str] = []
    for a in load_registry().archetypes:
        try:
            load_preset(a.id)
        except (FileNotFoundError, KeyError, ValueError):
            continue
        out.append(a.id)
    return out
