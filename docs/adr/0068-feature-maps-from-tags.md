# 68. Feature maps from image-level tags (M33)

- Status: accepted (M33, stage 4 of [ADR 0063](0063-specimen-work-restarted-in-stages.md))
- Date: 2026-10-24
- Builds on: [ADR 0066](0066-reference-library-and-labelling.md), [ADR 0067](0067-form-classifier-v1.md), [ADR 0019](0019-hand-marked-ground-truth.md)

## Context

Stage 4 asks where in a photo the features are: the quartz core, open cavity,
host rock, inclusions, and band boundaries. The reference library carries
image-level tags only (230 usable photos; quartz core 89, open cavity 56,
host rock 28, inclusions 24; moss 55, tube 26, plume 9 as forms). There are
no pixel masks.

A literature pass (2026-10-24) found no published image analysis that locates
features in agate photos. The nearest methods:

- A linear layer on DINOv2's frozen patch features segments everyday scenes
  well (ViT-S/14: mIoU 44.3 on ADE20k, 81.1 on VOC) [@oquab2023]. The model
  already used by the classifier returns these patch features (384 numbers per
  14 px square), so no new download is needed.
- Point labels spread through DINOv2 features segment textured coral photos
  (mIoU 59.5 with 10 points per image, 68.0 with 25) [@raine2024].
- Class activation maps locate objects from image-level labels alone, more
  coarsely than full supervision (top-5 localisation error 37.1% against
  26.7%), and tend to mark the most telling part rather than the whole object
  [@zhou2016].
- Boundary detectors are scored by precision and recall after matching to
  hand-marked boundaries within a distance tolerance [@arbelaez2011].

Measured on this PC (CPU): the image model takes 0.07 s at 224 px, 0.3 s at
518 px (37 x 37 patches) and 2.4 s at 896 px (64 x 64 patches). On a 60 mm
slab at 518 px a patch covers about 1.6 mm.

The owner chose to start from the tags alone, with no new annotation for
training (2026-10-24), over point labels, a click-to-outline tool, or a new
band-edge model.

## Decision

### 1. Feature maps from tags

For each feature with enough tagged photos (quartz core, open cavity, host
rock, inclusions, and moss and tube as forms; plume only if its 9 photos
suffice), a logistic layer on the patch features gives each patch a score.
It is trained as multiple-instance learning: a photo's score is the mean of
its top-scoring patches, and is fitted to the photo's tag. Photos are read
whole (no centre crop, unlike the classifier) at 518 px. The result is a
coarse heat map per feature, shown on the Classify screen as "rough
location".

### 2. Tested against taps, never against the tags

A map trained on tags can't be tested on the tags. The owner taps points on
about 40 library photos held out from training: points inside a feature and
points outside it. The score is how well each map ranks inside points above
outside points (0.5 is chance), reported per feature with two baselines that
catch shortcuts: chance, and a centre prior (quartz cores are often central,
so a map that just marks the middle must not pass). A feature's map is shown
only if it beats both. A synthetic photo with a known inserted region
(`agatesim.specimen.synthetic`) checks the pipeline end to end, and a photo
lacking the feature serves as the negative control.

The held-out photos are chosen once (`agatesim library hold-out`) and recorded
with the taps in `references/library-taps.toml`; the list can't change once
taps exist. Each feature gets about the same share of its photos (at least 2),
rarest first, then the rest are filled in a fixed hashed order. The 40 chosen
hold out 21 of 89 quartz-core photos, open cavity 14/56, host rock 8/28,
inclusions 6/24, moss 13/55, tube 6/26 and plume 2/9. Points are fractions of
the photo's width and height; a photo counts as tapped with at least 3 inside
and 3 outside points for each of its tagged features (about 5 each asked).

### 3. What is not promised

Patches of about 1.6 mm can't resolve 0.2 mm band boundaries or thin moss
filaments. Finer maps (896 px, or tiles) wait until the coarse maps pass,
with their time measured first. Maps describe appearance only and are never
evidence for a formation mechanism.

### 4. Band boundaries

The current boundary detector stays. Its score against the hand marks
(ADR 0019) is restated as precision, recall and F within a tolerance in mm
(0.2 and 0.5 mm), against a shuffled-boundary chance baseline. A new edge
model waits for better photos or for this score to show room to improve.

## Consequences

- No new model, download or training annotation. The owner taps ~40 photos for
  testing through the labelling screen (a tap mode to add).
- Maps cost about 0.3 s per photo at 518 px; training is seconds on the 230
  photos' cached patch features (about 2 MB per photo at float32, so the cache
  stays on disk, not in memory all at once).
- If tag-only maps fail the test, the next lever is point labels for
  training [@raine2024], reusing the same taps.

## Results (2026-10-24, first run)

`agatesim maps build` trains on the usable library photos minus the 40
held-out ones and any photo that probably shows the same specimen
(`specimen_group`). Patch features (384) are reduced to 64 whitened principal
components; a photo's score is the mean of its top 10% of patches; the fit
starts from the tagged-minus-untagged mean direction, because at zero every
patch ties and the fit stalls. Plume (7 training photos) gets no map. Cost:
86 s and 0.85 GB peak the first time (patch features of 230 photos, 157 MB on
disk); 9 s from the cache.

Mean per-photo ranking score on the owner's 841 taps, with the lower 95%
bound (paired bootstrap over photos) of the gain over chance and over the
centre prior:

| feature | test photos | map | centre prior | gain vs chance (low) | gain vs centre (low) | shown |
|---|---|---|---|---|---|---|
| quartz core | 21 | 0.91 | 0.70 | +0.34 | +0.08 | yes |
| open cavity | 11 | 0.85 | 0.85 | +0.21 | -0.20 | no |
| host rock | 7 | 0.89 | 0.21 | +0.30 | +0.47 | yes |
| inclusions | 6 | 0.78 | 0.47 | +0.09 | -0.08 | no |
| moss | 13 | 0.84 | 0.32 | +0.22 | +0.31 | yes |
| tube | 6 | 0.39 | 0.76 | -0.41 | -0.84 | no |

These settings were fixed before the taps were read and are not tuned on them:
tuning on the test taps would make them training data. Any later tuning uses
the training photos alone, or new taps.

On the Classify screen ("Rough location") only the maps that passed are
offered, read from the scores `build` stores with them, so a rebuilt map that
fails is hidden without a code change. The map dims the photo where a feature
is unlikely (a spotlight) instead of tinting where it is likely: a tint vanished
on warm-coloured agates.

## Results: band boundaries in mm (2026-10-24)

`scripts/score_boundaries.py` runs the app's analysis on the owner's marked
photos (3 photos, 4 lines, 164 marks; median marked spacing 0.36 mm) and scores
both finders within fixed tolerances (`benchmark.score_fixed`). The baseline
shuffles each line's found boundaries: same count and gaps, random order and
offset (200 draws). Summary numbers only, as the photos are private. Cost:
44 s, 1.73 GB peak (the full-resolution edge pass).

| finder | tolerance | found | precision | recall | F | shuffled F |
|---|---|---|---|---|---|---|
| boundary detector | 0.2 mm | 206 | 0.68 | 0.85 | 0.76 | 0.47 |
| boundary detector | 0.5 mm | 206 | 0.70 | 0.88 | 0.78 | 0.57 |
| band tracing | 0.2 mm | 56 | 0.55 | 0.19 | 0.28 | 0.24 |
| band tracing | 0.5 mm | 56 | 0.71 | 0.24 | 0.36 | 0.32 |

The detector beats its shuffles on all four lines (F 0.65–0.86 against
0.34–0.55 at 0.2 mm); the tracing is near chance, as ADR 0019 found. Two
cautions: the detector's settings were chosen on these same lines (ADR 0019),
so its figures are somewhat optimistic; and 0.5 mm exceeds the median marked
spacing, so at that tolerance nearly any boundary lands near some mark (hence
the higher shuffled F). The 0.2 mm figures are the ones to quote, and they sit
at the photos' resolution (0.22–0.25 mm, ADR 0065). As decided, the detector
stays; a new edge model waits for better photos or new marks on unseen lines.
