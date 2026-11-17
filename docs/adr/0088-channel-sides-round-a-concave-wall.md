# 88. Channel sides round a concave wall

- Status: accepted (owner, 2026-11-17: approved this fix from Nodule, this fix only)
- Date: 2026-11-17
- Builds on: [ADR 0077](0077-wall-features-clear-layer-and-channels.md) (wall channels),
  [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule needs)
- Spec: Nodule's ADR 0018 section 18

## Context

A wall channel's line is walked along the surface in short pieces, and each piece
gets a sideways direction: the wall distance's slope at the piece's midpoint, crossed
with the piece (`_place_channel`). Where the line bends round a concave stretch of
wall, a piece is a chord whose midpoint can lie outside the cavity. The wall distance
is flat there, so the slope is zero, the cross product is zero and the normalised
side is NaN. The side feeds the opening (`WallChannel._gap`), so every point nearest
that piece gets a NaN delay, a NaN arrival depth, and the grown stone opens a void.

Nodule found it while dealing escape tubes: 18 of 174 channel stones over 100 of its
sheets (vesicles 5 of 105, irregular stones 3 of 16, thunder eggs 10 of 36), each with
its bad piece's midpoint outside the cavity and a zero slope; one vesicle lost about
15 % of its volume to the void. In agatesim's own terms it shows without a clear layer:
6 of 60 seeds of `nodule-irregular`, 4 of 60 of `vesicle-lobate` (size 50 mm, line
10 mm). With a 1.5 mm clear layer the line sits deeper and none of those seeds fails.

## Decision

A piece whose midpoint slope is below `FLAT_SLOPE` (1e-6; on the surface it is near 1)
takes the mean slope at its two ends, which lie on the surface by construction
(`_sides`). Every other piece keeps its direction exactly, so channels that were sound
are unchanged and no other stone's result moves.

Test: `test_a_line_bent_round_a_concave_wall_keeps_finite_sides` (seed 9 of
`nodule-irregular`): the case is present (a piece's midpoint slope is zero), every side
is a finite unit vector across its piece, and the channel adds under 0.1 % void.

## Consequences

- Channel stones that opened voids now grow as intended; Nodule can drop its placement
  guard or keep it for the "no place on this cavity's wall" error.
- The ends' mean slope is a stand-in for the wall's facing at the chord; on a sharp
  crease the two ends face apart and the mean is their bisector. Effective, not
  physical.
