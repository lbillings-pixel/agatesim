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
