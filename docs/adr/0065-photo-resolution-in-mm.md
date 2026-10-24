# 65. Photo resolution in mm, not band spacing in pixels

- Status: accepted (amends [ADR 0064](0064-a-photo-quality-gate.md) before M31)
- Date: 2026-10-24

## Context

The owner's eight photos showed three quirks in the gate (ADR 0064). Band
spacing came out as whole pixels (6, 7 or 8), right at the 8 px calibration
limit. Noise sat on the 1-grey-level floor on the two most JPEG-blocky photos.
The fine-bands score read about 0 on all of them.

A closer look found a deeper problem. Band spacing read 6-8 px on every photo,
although the faces span 0.2 to 1.5 Mpx. On the synthetic photo, shrinking it
from 1 to 0.3 times moved the spacing only from 6.1 to 8.2 px: as finer bands
blur away, only coarser ones are counted, so the spacing settles at a few times
the blur. Adding a phone-like 1.2 px blur before scoring gave the same picture
(5.9-8.9 px) and also took the fine-bands score to about 0 and the noise to its
floor, exactly as on the owner's photos. A phone's own smoothing (demosaicing,
noise reduction, JPEG) removes the evidence of lost bands before any score can
count it. So neither score can say whether a phone photo resolves the bands.

The edge width at the specimen's rim can. It measured 3.0-3.4 px on all eight
photos (a perfect edge reads about 2.4 px), and with the ruler it converts to
millimetres on the face.

## Decision

- Turns along a profile are placed to a fraction of a pixel (the vertex of a
  parabola through the turn and its neighbours), so spacing is no longer whole
  pixels.
- A new score, **resolution** (mm): the edge width times the face's mm per
  pixel, about the thinnest band the photo can show. It needs the ruler.
- Calibration judges resolution, with effective limits fit at 0.2 mm or finer,
  borderline to 0.4 mm. Its band-spacing and fine-bands limits are dropped.
  Assumption, stated as no source sets it: agate's micro-banding is about
  100 µm [@cartwright2026], and calibration (M34) will compare photos with
  simulations blurred to the photo's own resolution, so twice that is
  accepted as fit.
- Classification keeps band spacing and fine bands as rough cautions; without
  a ruler nothing better is measurable.
- The noise floor stays. It is documented as a lower bound: where processing has
  smoothed the finest scale, contrast to noise is flattered, and the JPEG
  blocking score is what flags it.
- `QUALITY_VERSION` 3 re-scores cached photos.

## Consequences

- The three photos with a ruler read 0.22-0.25 mm: borderline for calibration
  (nodule-3 was fit before). The advice is to move closer or use a macro lens.
- Scoring cost is unchanged.
- Calibration (M34) should take each photo's resolution as an input and blur
  the simulations to match, rather than assume bands are fully resolved.
