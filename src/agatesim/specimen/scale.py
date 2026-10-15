"""Photo scale: two clicks on a ruler, corrected for the specimen face standing
higher than the ruler.

A camera at height D above the ruler sees an object at height h above it
magnified by D / (D - h). D follows from the ruler's own scale and the lens's
35 mm-equivalent focal length f: a pixel spans p = D · d35 / (f · d_px) on the
ruler plane, where d35 = 43.27 mm is the diagonal of a 35 mm frame and d_px the
image diagonal in pixels. So D = p · f · d_px / d35.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

FRAME_DIAGONAL_35MM = math.hypot(36.0, 24.0)  # 43.27 mm


class Calibration(BaseModel):
    """Two points on the ruler (working-image pixels) and the distance between them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    p1: tuple[float, float]
    p2: tuple[float, float]
    distance_mm: float = Field(gt=0)
    face_height_mm: float = Field(
        default=0.0, ge=0, description="Height of the cut face above the ruler's surface."
    )

    def ruler_mm_per_px(self) -> float:
        px = math.dist(self.p1, self.p2)
        if px <= 0:
            raise ValueError("the two ruler points coincide")
        return self.distance_mm / px


def camera_height_mm(
    ruler_mm_per_px: float, focal_35mm: float, image_px: tuple[int, int], scale_factor: float
) -> float:
    """Camera height above the ruler plane, from the ruler scale and focal length.
    `image_px` is the working image size and `scale_factor` working/original."""
    original_diag = math.hypot(*image_px) / scale_factor
    original_mm_per_px = ruler_mm_per_px * scale_factor
    return original_mm_per_px * focal_35mm * original_diag / FRAME_DIAGONAL_35MM


def face_mm_per_px(
    calibration: Calibration,
    focal_35mm: float | None,
    image_px: tuple[int, int],
    scale_factor: float = 1.0,
) -> tuple[float, float | None]:
    """mm per working pixel on the specimen's face, and the camera height used
    (None when the focal length is unknown, so no correction is made)."""
    ruler = calibration.ruler_mm_per_px()
    if not calibration.face_height_mm or not focal_35mm:
        return ruler, None
    height = camera_height_mm(ruler, focal_35mm, image_px, scale_factor)
    if height <= calibration.face_height_mm:
        raise ValueError("face height exceeds the camera height implied by the ruler")
    return ruler * (height - calibration.face_height_mm) / height, height
