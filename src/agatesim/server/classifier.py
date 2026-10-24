"""The learned form classifier in the app (ADR 0067): its answers on a photo,
and retraining after new labels. The owner's corrections to their own photos are
labels kept beside those photos (classify.own_label_path), never in the
repository (ADR 0066)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from numpy.typing import NDArray

from agatesim import classify, estimate, progress
from agatesim.server.tasks import TaskHeader


class ClassifierService:
    """The image model and the trained classifier, loaded once and reloaded
    when the classifier file changes."""

    def __init__(
        self,
        specimens: Path,
        models_dir: Path = classify.MODELS_DIR,
        embedder: Callable[[], classify.Embedder] | None = None,
    ) -> None:
        self.specimens = specimens
        self.models_dir = models_dir
        self.model_path = models_dir / classify.MODEL_PATH.name
        self.classifier_path = models_dir / classify.CLASSIFIER_PATH.name
        self._make_embedder = embedder or (lambda: classify.OnnxEmbedder(self.model_path))
        self._embedder: classify.Embedder | None = None
        self._classifier: tuple[int, classify.Classifier] | None = None
        self._lock = threading.Lock()
        self._training = threading.Lock()

    def model_ready(self) -> bool:
        return self._embedder is not None or self.model_path.exists()

    def embedder(self) -> classify.Embedder:
        with self._lock:
            if self._embedder is None:
                self._embedder = self._make_embedder()
            return self._embedder

    def classifier(self) -> classify.Classifier | None:
        if not self.classifier_path.exists():
            return None
        stamp = self.classifier_path.stat().st_mtime_ns
        with self._lock:
            if self._classifier is None or self._classifier[0] != stamp:
                self._classifier = (stamp, classify.Classifier.load(self.classifier_path))
            return self._classifier[1]

    def not_ready(self) -> str | None:
        """Why there are no answers yet, or None."""
        if not self.model_ready():
            return "The image model isn't downloaded yet (84 MB, once): `agatesim classify fetch`."
        model = self.classifier()
        if model is None:
            return "The classifier hasn't been trained yet: press Retrain."
        if model.embedder_key != self.embedder().key:
            return "The classifier was trained with another image model: press Retrain."
        return None

    def answer(self, rgb: NDArray[np.uint8]) -> dict[str, object]:
        why = self.not_ready()
        if why is not None:
            return {"ready": False, "why": why}
        model = self.classifier()
        assert model is not None
        a = classify.answer(model, self.embedder().embed(rgb))
        return {
            "ready": True,
            "likely": [{"form": f, "p": round(p, 3)} for f, p in a.likely],
            "ranked": [{"form": f, "p": round(p, 3)} for f, p in a.ranked],
            "trained_on": dict(zip(model.forms, model.real_counts, strict=True)),
            "threshold": classify.LIKELY,
        }

    def status(self) -> dict[str, object]:
        out: dict[str, object] = {
            "model": self.model_ready(),
            "trained": self.classifier_path.exists(),
            "own_labels": len(classify.own_labels(self.specimens)),
            "training": self._training.locked(),
        }
        if self.model_ready():
            cache = classify.EmbeddingCache(self.embedder(), self.models_dir)
            photos, sims = classify.missing_embeddings(cache, self.specimens)
            out["estimate"] = estimate.train_classifier(photos, sims).to_json()
        return out

    def train(self) -> dict[str, object]:
        if not self.model_ready():
            raise HTTPException(409, "download the image model first: `agatesim classify fetch`")
        if not self._training.acquire(blocking=False):
            raise HTTPException(409, "the classifier is already being retrained")
        try:
            embedder = self.embedder()
            cache = classify.EmbeddingCache(embedder, self.models_dir)
            with progress.span(0.0, 0.95, "embedding photos"):
                real, sims, forms = classify.gather(embedder, self.specimens, cache)
            with progress.span(0.95, 1.0, "fitting"):
                model = classify.train(real + sims, forms, embedder.key)
            model.save(self.classifier_path)
            own = sum(1 for e in real if e.group.startswith("own/"))
            return {"photos": len(real), "own_photos": own, "simulated": len(sims)}
        finally:
            self._training.release()


def classifier_router(service: ClassifierService, tasks: progress.Registry) -> APIRouter:
    router = APIRouter(prefix="/api/classifier")

    @router.get("")
    def status() -> dict[str, object]:
        return service.status()

    @router.post("/train")
    def train(task: TaskHeader = None) -> dict[str, object]:
        with tasks.track(task):
            return service.train()

    return router
