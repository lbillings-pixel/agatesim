"""The reference library's labelling API (ADR 0066).

Only the openly licensed library photos are served here, never the owner's
specimens, so this screen is safe to use over the remote link.
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from agatesim.archetypes.registry import load_registry
from agatesim.library import (
    FEATURES,
    IMAGES_DIR,
    LABELS_TOML,
    LIBRARY_TOML,
    Label,
    LibraryImage,
    load_labels,
    load_library,
    save_label,
)
from agatesim.taps import (
    TAPS_TOML,
    TRAIN_TAPS_TOML,
    FeatureTaps,
    Kind,
    load_taps,
    save_taps,
    tapped,
    targets,
)


def library_router(
    library_toml: Path = LIBRARY_TOML,
    labels_toml: Path = LABELS_TOML,
    images_dir: Path = IMAGES_DIR,
    taps_toml: Path = TAPS_TOML,
    train_taps_toml: Path = TRAIN_TAPS_TOML,
) -> APIRouter:
    router = APIRouter(prefix="/api/library")
    lock = threading.Lock()

    def image(image_id: str) -> LibraryImage:
        if not library_toml.exists():
            raise HTTPException(404, "the library list hasn't been built")
        try:
            return load_library(library_toml).get(image_id)
        except KeyError:
            raise HTTPException(404, f"no library image {image_id!r}") from None

    def local(img: LibraryImage) -> Path:
        return images_dir / img.path.name

    @router.get("")
    def index() -> dict[str, object]:
        """Every library photo with its guesses and labels, and the choices."""
        images = load_library(library_toml).images if library_toml.exists() else ()
        labels = load_labels(labels_toml)
        return {
            "forms": [{"id": a.id, "name": a.name} for a in load_registry().archetypes],
            "features": list(FEATURES),
            "images": [
                {
                    "id": i.id,
                    "title": i.title,
                    "source": i.source,
                    "author": i.author,
                    "licence": i.licence,
                    "licence_url": i.licence_url,
                    "guesses": list(i.guesses),
                    "fetched": local(i).exists(),
                    "label": labels[i.id].model_dump() if i.id in labels else None,
                }
                for i in images
            ],
        }

    def taps_path(kind: Kind) -> Path:
        return taps_toml if kind == "test" else train_taps_toml

    @router.get("/taps")
    def taps_index(kind: Kind = "test") -> dict[str, object]:
        """A tap set's photos: the held-out test photos (ADR 0068) or the
        training photos (ADR 0070), with what to tap and the taps so far."""
        labels = load_labels(labels_toml)
        held = load_taps(taps_path(kind), kind)
        out: list[dict[str, object]] = []
        for image_id in held.photos:
            label = labels.get(image_id)
            taps = held.taps.get(image_id, {})
            out.append(
                {
                    "id": image_id,
                    "targets": targets(label) if label else [],
                    "taps": {f: t.model_dump() for f, t in taps.items()},
                    "done": tapped(label, taps),
                }
            )
        return {"photos": out}

    @router.put("/{image_id}/taps")
    def put_taps(
        image_id: str, taps: dict[str, FeatureTaps], kind: Kind = "test"
    ) -> dict[str, object]:
        image(image_id)
        with lock:
            label = load_labels(labels_toml).get(image_id)
            try:
                saved = save_taps(image_id, label, taps, taps_path(kind))
            except ValueError as e:
                raise HTTPException(422, str(e)) from None
        return {"taps": {f: t.model_dump() for f, t in saved.items()}, "done": tapped(label, saved)}

    @router.get("/{image_id}/image")
    def photo(image_id: str) -> FileResponse:
        path = local(image(image_id))
        if not path.exists():
            raise HTTPException(404, "not fetched yet: run `agatesim library fetch`")
        return FileResponse(path, headers={"Cache-Control": "max-age=86400"})

    @router.put("/{image_id}/label")
    def put_label(image_id: str, label: Label) -> dict[str, object]:
        image(image_id)
        with lock:
            try:
                save_label(image_id, label, labels_toml)
            except ValueError as e:
                raise HTTPException(422, str(e)) from None
        return label.model_dump()

    @router.delete("/{image_id}/label", status_code=204)
    def clear_label(image_id: str) -> None:
        image(image_id)
        with lock:
            save_label(image_id, None, labels_toml)

    return router
