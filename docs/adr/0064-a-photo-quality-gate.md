# 64. A photo quality gate, a specimen library, and uploads without location

- Status: accepted (M30, stage 1 of [ADR 0063](0063-specimen-work-restarted-in-stages.md)); calibration limits amended by [ADR 0065](0065-photo-resolution-in-mm.md)
- Date: 2026-10-24

## Context

ADR 0063 asks for measured quality scores on every photo, validated on
synthetic photos degraded on purpose, and badges that say which uses a photo is
fit for and why not. It also lists loose ends for this stage: a Library apart
from the per-photo work, delete and rename, and uploads stored without GPS.

## Decision

### 1. Scores (`agatesim.specimen.quality`)

Each score is measured on the cut face at the photo's own resolution, without
tracing a band. Bands are read from 240 short profiles straight across them, each
along the structure-tensor normal [@bigun1987] of a window around a random point
of the face (windows with no clear direction are skipped).

| Score | Measure | Why this one |
|---|---|---|
| Band spacing (px) | median distance between neighbouring turns of brightness along the profiles, a turn rising or falling by 3× the noise and half the profile's spread | one band's thickness, as `band_statistics` counts it |
| Fine bands | share of the profiles' band detail (periods 2-64 px) at periods under 4 px, after white noise's expected share is taken off | bands finer than the pixels can't be counted, so a photo from too far reads as coarser-banded; detail at the pixel limit gives it away |
| Band contrast | median interquartile range of brightness along the profiles, over the noise | selects nothing: noise alone scores about 1.35 |
| Sharpness | full width at half maximum of the brightness slope across the specimen's rim | the rim is a sharp step on the face's plane; band edges can't be used, as blur erases fine bands and the ratio to what remains hides it |
| Noise | median absolute diagonal wavelet detail / 0.6745 [@donoho1994], in tiles on the face | fine texture counts too: either competes with the band edges |
| JPEG blocking | the strongest of the 8 column (and row) phases' mean jump over the median of the others | phase-free, so rotation and cropping don't hide it |
| Clipped highlights | share of the face with a channel at 254 or more | glare or over-exposure: nothing is recorded there |
| Colour cast | colour of the ruler's body along the two clicked points, taken to be grey, white or steel | the only neutral reference in the photo; a caution, never a fail |
| Scale | the ruler has been clicked | needed for anything in mm |

A grey-edge colour estimate over the whole photo was tried and dropped: it reads
the agate's own colour (and a blue cloth's) as a cast.

### 2. Validation on degraded synthetic photos

`synthetic.degrade` takes a synthetic photo (fortification, bands 7 px apart)
again with fewer pixels, blur, noise, a cast, a glare spot or harsh JPEG. Results:

| Damage | Score that responds | Clean → damaged |
|---|---|---|
| shrink 0.5, 0.4, 0.25 | band spacing; fine bands | 6 → 4 px; 3% → 5%, 14%, 20% |
| blur σ 1, 2, 4 px | sharpness | 3.0 → 3.8, 5.5, 8.6 px |
| noise σ 10, 20, 40 | contrast/noise | 8.4 → 4.8, 3.2, 2.0 |
| JPEG quality 50, 20, 8 | blocking | 1.04 → 1.20, 1.52, 1.94 |
| glare 2%, 10% of the slab | clipped | 2% → 3%, 9.5% |
| channel gains (1.2, 1, 0.8) | ruler cast | 25% → 40% (the synthetic ruler is tan) |

Noise, blur and enlargement don't read as fine bands (0-1%). Upscaled 2.88× (a
12 MP photo), the spacing scales to 16 px (truth about 20). A plain grey face
with noise is not fit (negative control). On two open-licence museum photos
(5,000-6,500 px wide) whose face was found, sharpness is 3.9 and 5.5 px and
spacing 24 and 17 px; on the others' dark backgrounds the automatic outline
failed, which the user's click on the specimen fixes.

### 3. Badges

Two uses, each with effective (fit, borderline) limits set on the photos above:

| Score | Classification | Calibration |
|---|---|---|
| Band spacing, at least | 5, 3.5 px | 8, 5 px |
| Fine bands, at most | 10%, 18% | 6%, 10% |
| Contrast/noise, at least | 3, 2 | 5, 3 |
| Sharpness / spacing, at most | 0.75, 1.0 | 0.6, 0.75 |
| Sharpness, at most | 9, 13 px | 6, 9 px |
| Clipped, at most | 5%, 15% | 1%, 5% |
| Blocking, at most | 1.6, 2.2 | 1.25, 1.6 |
| Scale | not needed | needed |
| Ruler cast | ignored | a caution above 10% |

A badge is the worst of its scores. Each reason carries advice (move closer,
focus on the face, lower the ISO, lower the exposure, save at full quality, click
the ruler, set the white balance), so the badges double as photography advice.
The limits are a first setting from synthetic photos; the owner's photos and the
reference library (M31) may move them, which needs no ADR until a stage relies
on them (calibration, M34).

### 4. The Specimens screen

- **Library**: every photo as a card with a thumbnail, its two badges and, on
  "Why", the reasons and tips; rename; delete in two clicks, which moves the
  photo and its settings to `specimens/.agatesim/deleted/` (nothing is erased);
  uploads. Unscored photos are scored one at a time; scores are cached beside the
  photo, keyed by file, scale and specimen pick (`QUALITY_VERSION` redoes them).
- **Classify**: the per-photo work as before, with the badges and tips above the
  photo, re-scored when the scale or specimen pick is saved.

### 5. Uploads without location

`photo.strip_metadata` stores a JPEG's own segments without EXIF (GPS among it),
XMP, IPTC, comments, MPF blocks or images appended after the first (depth or gain
maps carry their own metadata), keeping only the orientation and the 35 mm focal
length in a new, minimal EXIF block. JPEG pixels are kept bit for bit (no
re-encoding, so the blocking score stays honest); PNGs are re-saved in their own
mode. Photos already in the folder are left as they are; stripping them is the
owner's call.

## Consequences

- Scoring a 12 MP photo takes about 0.9 s and 80 MB at peak (one float32
  brightness channel; everything else in tiles and short profiles).
- Bands far below the pixels are still invisible: the fine-bands score flags
  detail piled up at the limit, not bands the photo lost altogether.
- `analysis_ready` in the image catalogue can be replaced by these badges (M31).
- Procedural and quality results say nothing about formation mechanisms.
