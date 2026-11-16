# 87. A floor sized by the wall alone

- Status: accepted (owner, 2026-11-16: approved this fix from Nodule, this fix only)
- Date: 2026-11-16
- Builds on: [ADR 0025](0025-inclusions-in-3d.md) (inclusions in 3D), [ADR 0053](0053-stick-agate-in-3d-colour-in-every-view-wider-randomize.md)
  (sticks in 3D), [ADR 0080](0080-slow-band-growth-round-plumes.md) (inclusions in the
  growth solid),
  [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule needs)
- Spec: Nodule's ADR 0018 section 15

## Context

In a 3D procedural run a settling stage lays down a volume: its growth (mm) times the
surface it would have lined, counted as the open reference points within one spacing
of the solid so far. That solid includes inclusions hanging in the open space
(dendrites since ADR 0025, wrapped at their own rate since ADR 0080; sticks), so their
surface was counted too. Nodule found the
fault: a floor set after early crystals rose from 0.40 to 0.60-0.69 of a stone's
height, and after moss on one stone filled the whole cavity (Nodule ADR 0018 s.15).
Nodule worked round it for crystals by dividing the floor's growth by a measured
factor per habit; no factor fits moss, whose surface varies too much.

Inclusions add surface, not silica supply: the floor should hold what it would without
them. No source gives a rule for this; it is the model's own consistency.

## Decision

1. `settling_area` (3D, `volume/growth.py`) counts the open shell next to the wall, bed,
   balls and tubes, leaving out inclusions (the solid's `aggregates`). A run without
   inclusions is unchanged, to the bit (the same solid is used).
2. Where the floor's top lands is still found among the open points with the
   inclusions in place, so the floor fills round them and their volume lifts it a
   little.
3. 2D runs are not changed (Nodule uses 3D; no fault was reported there).

## Check

Round 30 mm cavity, stick stage then a settling pulse (48-cell volume; floor = points
laid during the settling steps): 0.203 of the interior without sticks, 0.224 with
sticks (the sticks' own volume and the floor filling round them), and 0.615 with the
old sizing. Test: `test_a_floor_after_sticks_holds_what_it_would_without_them`, with
its negative control (the old sizing swapped back in must exceed 1.3 x the stone
without sticks).

## Consequences

- Nodule can drop its per-habit floor factor for crystals and needs none for moss or
  plumes; it re-measures its floors after moving its pin.
- Spherulite balls and quartz crystals still count, as before (not reported as a
  fault; a later change if one is).
- Procedural only, appearance only: never evidence for a formation mechanism.
