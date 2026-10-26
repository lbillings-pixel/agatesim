# 70. Feature maps from point labels (M33 follow-up)

- Status: accepted (2026-10-25); results and tag fixes in [ADR 0071](0071-tag-quality-for-the-maps.md)
- Date: 2026-10-25
- Builds on: [ADR 0068](0068-feature-maps-from-tags.md)

## Context

ADR 0068 trained a feature map per tag from image-level tags alone and tested
it on the owner's taps on 40 held-out photos. Three maps passed (quartz core,
host rock, moss); three failed: open cavity and inclusions beat chance but not
the centre prior, and tube scored below chance. Plume got no map (7 training
photos). ADR 0068 named the next lever: point labels for training
[@raine2024], on photos outside the test set, since test taps must stay
test-only.

## Proposal

### 1. A training tap set, apart from the test set

About 40 more photos from the training pool (labelled usable, not held out,
and not of the same specimen as a held-out photo, `specimen_group`), chosen as
the test set was (hashed order, rarest feature first) but weighted towards the
maps that failed: open cavity, inclusions, tube and plume, at least 6 photos
each where the library has them; the rest spread over the others. The list and
its taps go in a new file, `references/library-train-taps.toml`, so the test
file is never touched. The list is fixed once taps exist, as for the test set.

### 2. Tapping in the same screen

The Classify screen's tap mode gets a switch, "Test photos / Training photos".
Taps are the same: points inside a tagged feature and points outside it, on
the stone, at least 3 of each per feature.

### 3. Training on points as well as tags

Each map's fit adds a patch-level term to the tag term: the patch under each
tapped point is fitted to 1 (inside) or 0 (outside) by logistic loss. Point
terms together weigh as much as the tag terms (fixed before any test score is
read). Everything else stays as in ADR 0068.

### 4. Tested as before

The rebuilt maps are scored on the unchanged test taps, against chance and the
centre prior, with the same bootstrap bounds; a map is shown only if it beats
both. Settings are fixed before the test taps are read, and no tuning uses them.

## Owner's choices (2026-10-25)

1. About 40 training photos, not 20 for a first look.
2. Weighted towards the failed maps (open cavity, inclusions, tube, plume),
   not all features evenly.

## Consequences

- No new model, download or dependency. Training stays seconds from cached
  patch features; the new photos' features are computed once (~0.4 s each).
- Point labels are appearance only, never evidence for a formation mechanism.
- If tube still fails with points, its photos may be too few or too varied for a
  map; the next step would be more tube photos, not more tuning.

## Implementation (2026-10-25)

- `agatesim library train-set` chose 40 photos (`taps.choose_training_set`)
  from the 104 usable tagged photos of no held-out specimen: 6 each of the failed
  maps first, rarest first, then 2 each of the others, then hashed order. With
  overlaps the list holds open cavity 15, inclusions 6, tube 11, plume 6 (of 7),
  quartz core 21, host rock 6, moss 11. It is in
  `references/library-train-taps.toml` and is fixed once tapped.
- Specimens > Reference labels has a "Taps" mode with a "test photos /
  training photos" switch; the API takes `?kind=train`.
- `maps._fit_one` adds the mean logistic loss of the patch under each tap
  (inside 1, outside 0); the tag terms' weights sum to 1, so the points weigh as
  much as the tags. With no training taps the fit is unchanged. A synthetic test
  where the tag cannot tell two always-paired spots apart shows the taps decide
  it, and reversed taps teach the reverse (negative control).
- Next: the owner taps the 40 training photos; then `build` retrains and scores
  on the unchanged test taps (`agatesim maps build`).
