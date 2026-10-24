"""Specimen photos in the web app: list, upload, rename, delete, score,
view, analyse, replicate.

Photos live in a folder on the user's machine (by default `specimens/`, which is
gitignored). Uploads are stored without location or other metadata (only the
orientation and focal length are kept), and the app serves them only as
metadata-free images. It saves its own settings for each photo (scale, host,
which way was up) and its quality scores beside them in `.agatesim/`; deleted
photos move to `.agatesim/deleted/`.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from numpy.typing import NDArray
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from agatesim.archetypes import Host
from agatesim.classify import own_label_path
from agatesim.library import Label, check_label
from agatesim.render import render_slab
from agatesim.server.classifier import ClassifierService
from agatesim.simulate import simulate
from agatesim.specimen.benchmark import Transect, compare, score_along
from agatesim.specimen.edges import EdgeMap, boundary_edges, edge_crossings
from agatesim.specimen.fit import replicate
from agatesim.specimen.identify import NOT_FROM_PHOTOS, identify
from agatesim.specimen.observe import Observation, band_map, observe
from agatesim.specimen.photo import Photo, load_photo, strip_metadata
from agatesim.specimen.quality import assess, badges
from agatesim.specimen.scale import Calibration, face_mm_per_px
from agatesim.specimen.segment import segment
from agatesim.stats import band_statistics

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,80}\.(?:jpe?g|png)$", re.IGNORECASE)
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
VIEW_LONG_SIDE = 1600  # the working image the UI shows and clicks on
THUMB_LONG_SIDE = 360
THUMBS = 200
CACHE = 4
REPLICA_RESOLUTION = 512
CLASSIFY_LONG_SIDE = 1024  # as the classifier's training photos were read
QUALITY_VERSION = 3  # raise when the scores change, so cached ones are redone


class Rename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str


class SpecimenSettings(BaseModel):
    """What the user has told us about a photo."""

    model_config = ConfigDict(extra="forbid")

    calibration: Calibration | None = None
    host: Host = Host.VOLCANIC
    up_deg: float = Field(default=90.0, description="Which way was up (90 = up the photo).")
    seed: tuple[float, float] | None = Field(
        default=None, description="A point on the specimen (working-image px), if needed."
    )
    transects: list[Transect] = Field(
        default=[], description="Lines with hand-marked band boundaries."
    )


def _png(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def _data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _transect_json(
    obs: Observation, transect: Transect, edges: EdgeMap | None
) -> dict[str, object]:
    traced, result = compare(obs, transect)
    found = edge_crossings(edges, transect) if edges else []
    return {
        "traced": [round(t, 5) for t in traced],
        "score": result.to_json(),
        "edges": [round(t, 5) for t in found],
        "edge_score": score_along(obs, transect, found).to_json(),
    }


def specimen_router(folder: Path, classifier: ClassifierService | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/specimens")
    photos: OrderedDict[str, Photo] = OrderedDict()
    observations: OrderedDict[str, Observation] = OrderedDict()
    edge_cache: dict[str, EdgeMap] = {}
    detail_cache: dict[str, bytes] = {}
    thumbs: OrderedDict[str, bytes] = OrderedDict()

    def path_of(name: str) -> Path:
        if not NAME.fullmatch(name):
            raise HTTPException(404, f"no specimen {name!r}")
        path = folder / name
        if not path.is_file():
            raise HTTPException(404, f"no specimen {name!r}")
        return path

    def settings_path(name: str) -> Path:
        return folder / ".agatesim" / f"{name}.json"

    def quality_path(name: str) -> Path:
        return folder / ".agatesim" / f"{name}.quality.json"

    def sidecars(name: str) -> list[Path]:
        return [settings_path(name), quality_path(name), own_label_path(folder, name)]

    def saved_settings(name: str) -> SpecimenSettings:
        p = settings_path(name)
        if p.exists():
            return SpecimenSettings.model_validate_json(p.read_text("utf-8"))
        return SpecimenSettings()

    def quality_key(name: str, settings: SpecimenSettings) -> str:
        stat = path_of(name).stat()
        told = settings.model_dump_json(include={"calibration", "seed"})
        return f"{QUALITY_VERSION}:{stat.st_size}:{stat.st_mtime_ns}:{told}"

    def cached_quality(name: str, settings: SpecimenSettings) -> dict[str, Any] | None:
        p = quality_path(name)
        if not p.exists():
            return None
        try:
            saved = json.loads(p.read_text("utf-8"))
        except ValueError:
            return None
        return saved if saved.get("key") == quality_key(name, settings) else None

    def forget(name: str) -> None:
        """Drop everything cached for a photo (after a rename or delete)."""
        photos.pop(name, None)
        detail_cache.pop(name, None)
        thumbs.pop(name, None)
        for cache in (observations, edge_cache):
            for key in [k for k in cache if k.startswith(name)]:
                del cache[key]

    def photo(name: str) -> Photo:
        if name not in photos:
            if len(photos) >= CACHE:
                photos.popitem(last=False)
            photos[name] = load_photo(path_of(name).read_bytes(), VIEW_LONG_SIDE)
        photos.move_to_end(name)
        return photos[name]

    def analyse_with(name: str, settings: SpecimenSettings) -> tuple[Observation, dict[str, Any]]:
        if settings.calibration is None:
            raise HTTPException(422, "set the scale first: click two points on the ruler")
        p = photo(name)
        try:
            mm_per_px, camera = face_mm_per_px(
                settings.calibration, p.focal_35mm, (p.shape[1], p.shape[0]), p.scale_factor
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        seg = segment(p.rgb, settings.seed)
        if len(seg.outline) < 3:
            raise HTTPException(422, "couldn't find the specimen: click on it to help")
        try:
            obs = observe(
                p.rgb, seg, mm_per_px, host=settings.host, up_deg=settings.up_deg, name="specimen"
            )
        except ValueError as e:
            raise HTTPException(422, f"couldn't analyse the specimen: {e}") from e
        key = name + settings.model_dump_json(exclude={"transects"})
        observations[key] = obs
        if len(observations) > CACHE:
            observations.popitem(last=False)
        return obs, {
            "mm_per_px": mm_per_px,
            "camera_height_mm": camera,
            "seg_outline": seg.outline,
            "seg_mask": seg.mask,
        }

    def edges_of(name: str, mask: NDArray[np.bool_]) -> EdgeMap:
        key = name + str(hash(mask.tobytes()))
        if key not in edge_cache:
            full = load_photo(path_of(name).read_bytes(), 10**6)
            edge_cache.clear()
            edge_cache[key] = boundary_edges(full.rgb, mask, full.shape[1] / mask.shape[1])
        return edge_cache[key]

    @router.get("")
    def list_specimens() -> list[dict[str, object]]:
        if not folder.is_dir():
            return []
        out: list[dict[str, object]] = []
        for path in sorted(folder.iterdir()):
            if path.is_file() and NAME.fullmatch(path.name):
                quality = cached_quality(path.name, saved_settings(path.name))
                out.append(
                    {
                        "name": path.name,
                        "bytes": path.stat().st_size,
                        "has_settings": settings_path(path.name).exists(),
                        "badges": None if quality is None else quality["badges"],
                    }
                )
        return out

    @router.post("", status_code=201)
    async def upload(request: Request, name: str) -> dict[str, object]:
        if not NAME.fullmatch(name):
            raise HTTPException(
                422, "use a .jpg, .jpeg or .png name of letters, digits, . _ - and spaces"
            )
        data = await request.body()
        if not data or len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(422, "empty or too large (40 MB at most)")
        try:
            load_photo(data, 64)
            data = strip_metadata(data)
        except Exception as e:  # any decoding failure means it isn't a usable image
            raise HTTPException(422, "not a readable image") from e
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        if target.exists():
            raise HTTPException(409, f"{name} already exists")
        target.write_bytes(data)
        return {"name": name, "bytes": len(data)}

    @router.get("/{name}/photo")
    def photo_png(name: str) -> Response:
        return Response(photo(name).png(), media_type="image/png")

    @router.get("/{name}/thumb")
    def thumb(name: str) -> Response:
        """A small JPEG for the library (written from an array: no EXIF)."""
        if name not in thumbs:
            small = load_photo(path_of(name).read_bytes(), THUMB_LONG_SIDE)
            buffer = io.BytesIO()
            Image.fromarray(small.rgb).save(buffer, format="JPEG", quality=85)
            thumbs[name] = buffer.getvalue()
            if len(thumbs) > THUMBS:
                thumbs.popitem(last=False)
        return Response(thumbs[name], media_type="image/jpeg")

    @router.get("/{name}/detail")
    def photo_detail(name: str) -> Response:
        """The photo at full resolution, for zooming in to mark fine bands. A JPEG
        written from an array carries no EXIF. Clicks are still in working-image px."""
        if name not in detail_cache:
            full = load_photo(path_of(name).read_bytes(), 10**6)
            buffer = io.BytesIO()
            Image.fromarray(full.rgb).save(buffer, format="JPEG", quality=92)
            detail_cache.clear()
            detail_cache[name] = buffer.getvalue()
        return Response(detail_cache[name], media_type="image/jpeg")

    @router.get("/{name}/settings")
    def get_settings(name: str) -> SpecimenSettings:
        path_of(name)
        return saved_settings(name)

    @router.put("/{name}/settings")
    def put_settings(name: str, settings: SpecimenSettings) -> SpecimenSettings:
        path_of(name)
        p = settings_path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(settings.model_dump_json(indent=1), "utf-8")
        return settings

    @router.post("/{name}/rename")
    def rename(name: str, body: Rename) -> dict[str, object]:
        source = path_of(name)
        to = body.to.strip()
        if not NAME.fullmatch(to):
            raise HTTPException(
                422, "use a .jpg, .jpeg or .png name of letters, digits, . _ - and spaces"
            )
        same_kind = {".jpg": ".jpeg", ".jpeg": ".jpg"}
        old_ext, new_ext = source.suffix.lower(), Path(to).suffix.lower()
        if new_ext != old_ext and same_kind.get(old_ext) != new_ext:
            raise HTTPException(422, f"keep the {old_ext} ending")
        target = folder / to
        if target.exists() and target.name.lower() != name.lower():
            raise HTTPException(409, f"{to} already exists")
        forget(name)
        source.rename(target)
        for old, new in zip(sidecars(name), sidecars(to), strict=True):
            if old.exists():
                old.replace(new)
        return {"name": to}

    @router.delete("/{name}")
    def delete(name: str) -> dict[str, object]:
        """Move the photo and its settings to `.agatesim/deleted/`, so a mistake
        can be undone by hand."""
        source = path_of(name)
        bin_ = folder / ".agatesim" / "deleted"
        bin_.mkdir(parents=True, exist_ok=True)
        stem = name
        if (bin_ / name).exists():
            stem = time.strftime("%Y%m%d-%H%M%S ") + name
        forget(name)
        source.replace(bin_ / stem)
        for side in sidecars(name):
            if side.exists():
                side.replace(bin_ / (stem + side.name[len(name) :]))
        return {"deleted": name, "kept_in": f".agatesim/deleted/{stem}"}

    @router.post("/{name}/quality")
    def quality(name: str, settings: SpecimenSettings) -> dict[str, object]:
        """Scores of the photo and which uses it is fit for (cached beside it)."""
        cached = cached_quality(name, settings)
        if cached is not None:
            return {"quality": cached["quality"], "badges": cached["badges"]}
        p = photo(name)
        seg = segment(p.rgb, settings.seed)
        mm_per_px: float | None = None
        ruler = None
        if settings.calibration is not None:
            try:
                mm_per_px, _ = face_mm_per_px(
                    settings.calibration, p.focal_35mm, (p.shape[1], p.shape[0]), p.scale_factor
                )
                ruler = (settings.calibration.p1, settings.calibration.p2)
            except ValueError:
                pass
        full = load_photo(path_of(name).read_bytes(), 10**6)
        q = assess(full.rgb, seg.mask, seg.outline, mm_per_px=mm_per_px, ruler=ruler)
        del full
        out: dict[str, object] = {
            "quality": q.to_json(),
            "badges": [b.to_json() for b in badges(q)],
        }
        target = quality_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"key": quality_key(name, settings), **out}), "utf-8")
        return out

    @router.post("/{name}/analyse")
    def analyse(name: str, settings: SpecimenSettings) -> dict[str, object]:
        obs, info = analyse_with(name, settings)
        result = obs.result
        edges = edges_of(name, info["seg_mask"]) if settings.transects else None
        return {
            "mm_per_px": info["mm_per_px"],
            "camera_height_mm": info["camera_height_mm"],
            "outline_px": np.round(np.asarray(info["seg_outline"], dtype=np.float64), 1).tolist(),
            "size_mm": result.domain.cavity.size_mm,
            "outline_mm": np.round(obs.outline_mm, 3).tolist(),
            "host": settings.host.value,
            "band_map": _data_uri(_png(band_map(obs))),
            "stats": band_statistics(result).to_json(),
            "identification": [i.to_json() for i in identify(result)],
            "not_from_photos": NOT_FROM_PHOTOS,
            "transects": [_transect_json(obs, t, edges) for t in settings.transects],
        }

    @router.post("/{name}/classify")
    def classify_photo(name: str) -> dict[str, object]:
        """The learned classifier's answer (ADR 0067): appearance only."""
        if classifier is None:
            return {"ready": False, "why": "no classifier in this app"}
        rgb = load_photo(path_of(name).read_bytes(), CLASSIFY_LONG_SIDE).rgb
        return classifier.answer(rgb)

    @router.get("/{name}/label")
    def get_label(name: str) -> Label | None:
        path_of(name)
        p = own_label_path(folder, name)
        return Label.model_validate_json(p.read_text("utf-8")) if p.exists() else None

    @router.put("/{name}/label")
    def put_label(name: str, label: Label) -> Label:
        """The owner's label of their own photo, kept beside it (ADR 0066)."""
        path_of(name)
        try:
            check_label(label)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        p = own_label_path(folder, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(label.model_dump_json(), "utf-8")
        return label

    @router.delete("/{name}/label", status_code=204)
    def clear_label(name: str) -> None:
        path_of(name)
        own_label_path(folder, name).unlink(missing_ok=True)

    @router.post("/{name}/replicate")
    def make_replica(name: str, settings: SpecimenSettings) -> dict[str, object]:
        obs, _ = analyse_with(name, settings)
        fit = replicate(obs.result)
        config = fit.config.with_resolution(REPLICA_RESOLUTION)
        image = render_slab(simulate(config))
        return {
            "config": json.loads(config.model_dump_json()),
            "image": _data_uri(_png(image)),
            "stats": fit.stats.to_json(),
            "target": fit.target.to_json(),
            "mismatch": round(fit.mismatch, 3),
        }

    return router
