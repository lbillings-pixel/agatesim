"""A promptable segmentation model for the rim-finder (ADR 0074).

SAM 2.1 Hiera-Tiny [@ravi2025], the onnx-community export, run through ONNX
Runtime on the processor. Its four files (two graphs, each with its weights
beside it) are fetched on demand into references/models/sam2.1-tiny/
(gitignored), each checked against a pinned hash.

Given a box and points on a photo, it returns three candidate masks, its own
estimate of each one's overlap with the object (predicted IoU), and an
object-presence score. The photo is squashed to the encoder's 1024 x 1024
square, as the model's own preparation does, so masks map straight back.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim.classify import MEAN, MODELS_DIR, STD, fetch_model

SAM_DIR = MODELS_DIR / "sam2.1-tiny"
_BASE = (
    "https://huggingface.co/onnx-community/sam2.1-hiera-tiny-ONNX/resolve/"
    "814a066640debee5a91e70aa401fb8e17e030503/onnx/"
)
# File name -> SHA-256. A graph finds its weights by file name, so the names
# are kept as published.
FILES = {
    "vision_encoder.onnx": "4f30aacd3aaefbca81a0b7fe4c1fc96345570ea0a6f80ced599493d1b3be2e8c",
    "vision_encoder.onnx_data": "e83df9866a5afe68ea7f0f721f18f65137fc3acbf0da1c74e946d363e09c69cc",
    "prompt_encoder_mask_decoder.onnx": (
        "874414704c5d686db7d206a35f6e15d26563d50c8c4468fccc6739bd7e491dcf"
    ),
    "prompt_encoder_mask_decoder.onnx_data": (
        "e9874d900dd4134ed60eab1e97910327c2419e0b2954485d8fd6e7f1a1470f47"
    ),
}
ENCODER_PATH = SAM_DIR / "vision_encoder.onnx"
DECODER_PATH = SAM_DIR / "prompt_encoder_mask_decoder.onnx"


def fetched() -> bool:
    return all((SAM_DIR / name).exists() for name in FILES)


def fetch_sam() -> list[Path]:
    """Download the model's files once (about 155 MB). Returns those downloaded."""
    got: list[Path] = []
    for i, (name, sha256) in enumerate(FILES.items(), 1):
        path = SAM_DIR / name
        if fetch_model(_BASE + name, sha256, path, f"the segmentation model ({i} of {len(FILES)})"):
            got.append(path)
    return got


SIZE = 1024  # the encoder's square input
STABILITY_OFFSET = 1.0  # logit offset of SAM's stability score [@kirillov2023]


def prepare(rgb: NDArray[np.uint8]) -> NDArray[np.float32]:
    """A photo as the model expects it (its preprocessor_config.json): squashed
    to 1 x 3 x 1024 x 1024, bilinear, ImageNet mean and spread."""
    im = Image.fromarray(rgb).convert("RGB").resize((SIZE, SIZE), Image.Resampling.BILINEAR)
    a = (np.asarray(im, np.float32) / 255.0 - MEAN) / STD
    return a.transpose(2, 0, 1)[None].astype(np.float32)


@dataclass(frozen=True)
class Candidates:
    """The decoder's answer to one prompt."""

    logits: NDArray[np.float32]  # (3, 256, 256) mask logits over the whole (squashed) photo
    iou: NDArray[np.float32]  # (3,) predicted IoU of each mask
    object_score: float  # logit; above 0, an object is present

    def stability(self, k: int) -> float:
        """SAM's stability score of mask k: the mask at logit +1 over the mask at -1."""
        m = self.logits[k]
        return float((m > STABILITY_OFFSET).sum()) / max(float((m > -STABILITY_OFFSET).sum()), 1.0)

    def mask(self, k: int, size: tuple[int, int]) -> NDArray[np.bool_]:
        """Mask k at (width, height), from its logits scaled up bilinearly."""
        up = Image.fromarray(self.logits[k], mode="F").resize(size, Image.Resampling.BILINEAR)
        return np.asarray(up) > 0


class Sam:
    """The encoder and the prompt decoder on the processor (about 1.5 s and 0.9
    GB per photo for the encoder, 0.04 s per prompt for the decoder)."""

    def __init__(self) -> None:
        from agatesim._onnx import Session

        if not fetched():
            raise FileNotFoundError(f"the segmentation model isn't in {SAM_DIR}")
        self._encoder = Session(ENCODER_PATH, arena=False)
        self._decoder = Session(DECODER_PATH, arena=False)

    def embed(self, rgb: NDArray[np.uint8]) -> list[NDArray[np.float32]]:
        return self._encoder.run_named({"pixel_values": prepare(rgb)})

    def predict(
        self,
        embeddings: Sequence[NDArray[np.float32]],
        size: tuple[int, int],
        box: tuple[float, float, float, float],
        points: NDArray[np.float64],
        labels: NDArray[np.int64],
    ) -> Candidates:
        """Masks for a box (x0, y0, x1, y1) and points (n, 2) of (x, y), labelled
        1 on the object and 0 off it, all in pixels of a photo of `size` (w, h)."""
        sx, sy = SIZE / size[0], SIZE / size[1]
        feeds: dict[str, NDArray[np.generic]] = {
            "input_points": (points * [sx, sy])[None, None].astype(np.float32),
            "input_labels": labels[None, None].astype(np.int64),
            "input_boxes": (np.asarray(box) * [sx, sy, sx, sy])[None, None].astype(np.float32),
        }
        feeds |= {f"image_embeddings.{i}": e for i, e in enumerate(embeddings)}
        iou, logits, obj = self._decoder.run_named(feeds)
        return Candidates(logits[0, 0], iou[0, 0], float(obj[0, 0, 0]))
