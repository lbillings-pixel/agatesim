# 71. Tag quality for the feature maps: unsure tags, one map for moss and plume

- Status: accepted (2026-10-25)
- Date: 2026-10-25
- Builds on: [ADR 0066](0066-reference-library-and-labelling.md), [ADR 0068](0068-feature-maps-from-tags.md), [ADR 0070](0070-maps-from-point-labels.md)

## Context

The owner tapped 29 of the 40 training photos of ADR 0070. They tapped every
feature they could place with confidence and sent notes on the rest. Two
problems turned up.

- **Wrong and doubtful tags.** On 17 of the 40 photos, 22 map tags from earlier
  labelling rounds were wrong (7: the feature isn't there) or doubtful (15).
  Tube was hit hardest (5 tags). The maps learn chiefly from these tags: a tag
  says "this feature is somewhere in the photo", so a wrong tag teaches the map
  that ordinary agate looks like the feature. Tube, the worst map (ADR 0068), had
  the most doubtful tags.
- **The tap screen fought small features.** A feature had to get three inside
  taps, and a tap near an existing dot removed it. On a small feature the taps
  undid each other, so some could not be tapped at all.
- **Overlapping tags.** "Inclusions" is a catch-all that covers moss and plume.
  And in photos, moss and plume blur into each other. Our source treats both as
  growths inside the agate: moss filaments wrapped in chalcedony, and plume as
  silica-garden growth ([@goetze2020] §5.5). The registry sets
  plume apart by its feathery, upward-billowing shape. That difference is one of
  form, and the maps' patches (about 1.6 mm, ADR 0068) are too coarse to show it
  reliably. No source in the catalogue gives photo criteria for telling them
  apart, and none was searched for (owner's rule: state the assumption).

## Decision

1. **Unsure tags.** A label gets `unsure`: forms or features the owner could
   neither confirm nor rule out. An unsure tag is neither yes nor no: a photo
   sits out the training of any map whose only tags on it are unsure, and the tap
   screen doesn't ask for it. `reviewed` marks a photo whose map tags were
   checked. The owner's notes were applied to the 40 training photos: the 7
   wrong tags removed, the 15 doubtful ones made unsure, and all 40 marked
   reviewed.
2. **Small features.** Removing a dot is now its own tool ("remove a dot"), so
   taps never undo each other. A feature counts as tapped with one inside point
   and three outside. Taps already made on a tag later removed stay in the file,
   unused.
3. **A tag check.** Specimens > Reference labels gets a "Check tags" mode: for
   each photo, yes / no / not sure on each map tag. Tube, plume and moss photos
   come first. 123 photos are waiting (tube 15, plume 3, moss 44, host rock 21,
   open cavity 38, quartz core 68 tags). A photo left with no forms is marked
   "can't tell".
4. **One map for moss and plume; none for inclusions** (owner approved,
   2026-10-25). The maps are quartz core, open cavity, host rock, "moss or
   plume" and tube. "Moss or plume" learns from both tags, and its test taps are
   the moss and plume taps together (no test photo has both). The tags
   themselves are unchanged: moss and plume stay separate forms in the labels,
   the classifier (ADR 0067) and the archetype registry, where the simulator
   models them differently. Inclusions is still labelled but feeds no map. To
   undo, edit `taps.MAP_GROUPS`.

## Results (2026-10-25)

Scores on the unchanged test taps (ADR 0068). Map: the chance that an inside
tap outranks an outside one, averaged over photos. "Shown": beats both chance
and the centre prior.

| map | test photos | before (ADR 0068) | old tags + taps | fixed tags, no taps | fixed tags + taps | shown |
|---|---|---|---|---|---|---|
| quartz core | 21 | 0.91 | 0.95 | 0.89 | 0.95 | yes |
| open cavity | 11 | 0.85 | 0.99 | 0.89 | 0.99 | yes (was no) |
| host rock | 7 | 0.89 | 0.86 | 0.93 | 0.87 | yes |
| moss or plume | 15 | 0.84 (moss alone) | 0.90 | 0.78 | 0.89 | yes |
| tube | 6 | 0.39 | 0.64 | 0.66 | 0.76 | no |

- The taps drive most of the gain (open cavity, moss or plume). The tag fixes
  matter most for tube: 0.39 to 0.66 without taps, 0.64 to 0.76 with them. Tube
  now beats chance but only ties the centre prior (0.76), so it is still not
  shown.
- The "before" moss column is the moss map alone, so it isn't a like-for-like
  comparison. "Old tags" are the labels before part 1, scored with part 4's
  grouping.
- Cost: 8 s to build from cached patch features.

## Consequences

- Labels and taps are appearance only, never evidence for a formation mechanism.
- Tube's tags were the most often wrong, so the next step for tube is the tag
  check (part 3) on its 15 remaining tube photos. More tube photos come after
  that. Only 6 test photos carry tube taps, so its score is uncertain either way.
- An outside tap on moss can land on plume on the same photo (2 training photos
  carry both). In the shared map such a tap counts as "not moss or plume". This
  is accepted for now.
- The classifier still reads unsure forms as absent. Masking them there too is
  a possible follow-up.
