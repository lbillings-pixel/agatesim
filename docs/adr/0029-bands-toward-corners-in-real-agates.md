# 29. Do bands thin toward corners in real agates?

- Status: accepted (three photos; preliminary)
- Date: 2026-10-16
- Builds on: [ADR 0026](0026-corner-benchmark-from-high-resolution-photos.md), [ADR 0028](0028-regularised-h1-at-the-corner.md)

## Context

The regularised H1 (ADR 0028) turns corners sharply enough to match the photos,
but its corners lag behind the faces, so bands thin toward the corners. That is
a prediction the reference photos can test. A corner that keeps up with its
faces leaves each band the same thickness along the whole face.

## What was tried first, and why it was dropped

- **Spacing along the mitre against spacing on the faces.** Where a corner
  keeps up, bands along the mitre are 1/sin(φ/2) times as far apart as on a
  face. On synthetic corners this recovers a known lag. But on a procedural
  slab, whose corners keep up by construction, it read 0.63–0.81 instead of 1.
  Bands vary in thickness along a wall (the procedural model's texture does
  this too), so comparing spacing in two different places mixes in that
  variation. The model's lag is also not local: it is a gradual thinning along
  the whole face.
- **Band spacing along a face, by matching the band pattern** between stations.
  On procedural slabs it reads 1.05 (0.94–1.13 over 16 half-faces). But it
  can't read the regularised H1, whose bands cross at low angles, so the
  pattern changes along the face. Both measures were removed.

## Decision

**Measure one marker band.** A distinctive band that rings the polygon marks a
single moment in growth, so its thickness along a face is the growth over that
interval. In the model this is the front's advance between two times, which
gives a direct prediction.

- `agatesim.specimen.corner_fit.band_widths_along` measures a band's width
  across a face line, at 81 stations corner to corner. Gaps under 41 px (cracks
  across the band) are bridged, and widths are median-filtered over 7 stations.
- `face_thinning` gives the width a quarter of the way along the face from each
  corner over the width in the middle (stations 0.2–0.3 and 0.7–0.8, against
  0.4–0.6).
- Tested on synthetic bands of known taper, with cracks, plus a negative
  control: a uniform band must not read as thinning.
- **Marks are saved** in `references/images/corner_marks.toml`: the photo, the
  marker's colour, and the band's corners. The ADR 0026 corner positions were
  never saved, which is why this file exists.
  `scripts/marker_band_thinning.py` repeats the measurement.

**The model's prediction**, from the 2D corner runs of ADR 0028, is the front's
advance a quarter of the way along a face (12 screening lengths from the wall
corner, on a face 50 long) over its advance in the middle, in bands laid down
late: **0.68–0.78** across sets 2, 5 and 6 and two curvature values (grid
h = 0.025 or 0.05). Halving the grid spacing strengthens the thinning (set 5,
growth from t = 50 to 150: 0.85 at h = 0.025, 0.75 at h = 0.0125), so this range
is if anything an upper bound.

## Results

Three of the five photos have a marker that rings the polygon: an orange band
in n02 and n04, picked out by colour, and a thin milky band in the polygonal
agate, picked out as a smooth band brighter than its surroundings once the
uneven lighting is evened out (`kind = "bright"`). n01 and n03 have none.

| Photo | Face | Quarter-way width / mid-face width |
|---|---|---|
| n02 | top | 1.16, 1.04 |
| n02 | right, upper | 0.89, 1.06 |
| n02 | right, lower | 0.96, 1.12 |
| n02 | bottom | 1.79, 1.50 |
| n02 | left | 0.84, 0.90 |
| n04 | top-right | 1.00, 0.83 |
| n04 | bottom | 1.20, 1.04 |
| n04 | short left face | 1.03, 1.17 |
| n04 | top-left | 0.45, 0.94 |
| polygonal | upper-left | 1.27, 0.89 |
| polygonal | upper-right | 0.83, 0.97 |

The polygonal agate's lower faces are skipped: the thin band is missing on the
lower right and merges with its neighbour near the left corner.

- **Median over 22 half-faces on 11 faces: 1.02, with a 95% interval of
  0.92–1.11** (from resampling whole faces, since a face's two halves aren't
  independent). Four half-faces fall below 0.85, three only just (0.83–0.84),
  one well below (n04 top-left near its left corner, 0.45). n02's bottom band
  thickens toward both corners.
- So the marker bands mostly keep their thickness toward corners, as a corner
  that keeps up predicts. The regularised H1's 0.68–0.78 lies outside the
  interval.

## Caveats

- Three specimens, one marker each, corners marked by eye on gridded crops.
  The polygonal agate's thin band is about 10 px wide at the quarter
  resolution used, so its readings carry about 10% noise.
- Natural variation along a band is large (0.84–1.79 here), so single faces
  say little; the median does.
- The model's prediction depends on the cavity's size relative to the
  impurity screening length, which is unknown for real agates. In a smaller
  cavity, relative to that length, the thinning would spread over the whole
  face and could read weaker by this quarter-way measure.

## Consequences

- With ADR 0026 (sharp to moderately rounded mitres) and ADR 0028 (the
  regularised H1 makes bands thin toward corners), the photos favour corners
  that keep up with their faces: growth that every part of the wall sees
  equally, as in H1's boundary-layer form, rather than growth fed by diffusion
  through the cavity.
- Backlog: more specimens with marker bands, ideally photographed under even
  light.
