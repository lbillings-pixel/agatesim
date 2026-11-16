# 86. A reach that follows the local depth

- Status: accepted (owner, 2026-11-15: approved this change from Nodule, and the reading
  of floor stones in section 2 below)
- Date: 2026-11-15
- Builds on: [ADR 0081](0081-plume-reach-from-the-wall.md) (a reach in mm),
  [ADR 0025](0025-inclusions-in-3d.md) (3D aggregation),
  [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule needs)
- Spec: Nodule's ADR 0018 section 14

## Context

`dendrite_reach_mm` (ADR 0081) keeps branched inclusions within one distance of the wall
everywhere in a stone. Nodule's moss look sheets showed the fault: in a stone with a
small side lobe beside its main one, or with a large floor under a small pocket of
wall-lining bands, moss was the same size throughout. The owner asked that the size of
moss follow the subregion it grows in.

No source gives moss or plume sizes by position in a cavity; the rule below is an
assumption chosen for the look.

## Decision

1. **`dendrite_reach_share`** (3D, `effective`, default 0 = off, range [0, 1]):
   inclusions grow only where the distance from the wall is at most this share of the
   *local depth*. The local depth of a lattice cell is the largest wall distance reached
   by climbing from it: each cell points at its deepest neighbour of the 26, and the
   pointers are followed to a summit (`dendrites.basin_depth`). It is the half-width of
   the lobe or pocket the cell lies in. It applies together with `dendrite_reach_mm`.
2. **`dendrite_reach_floor`** (3D, `effective`, default 0 = none, range [0, 1)): the
   height, as a share of the cavity's, to which a floor later fills it. Above that level
   the depth is the lesser of the wall distance and the height above the level (the
   cavity left above the floor), and a climb never crosses the level; below it the depth
   is the whole cavity's. Inclusions above a floor are then sized to the pocket the
   wall-lining bands will fill, those in the floor region to the whole stone.
3. **`dendrite_reach_contrast`** (3D, `effective`, default 0, range [0, 4]): the share
   is further scaled by (local depth / deepest local depth) to this power, the deepest
   taken on each side of a floor's level (`dendrites.local_reach`). At 0 every lobe
   fills the same share of its own depth, so a side lobe looks like a scaled-down main
   one; Nodule's third moss look sheet showed this was too little contrast (owner,
   2026-11-15: "make the lobe contrast stronger"), and above 0 a shallow lobe fills a
   smaller share. Added with the owner's approval the same day.
4. **Assumptions:** the share and contrast are one number each per stone; lobes are told apart by summits
   of the wall distance, so the reach steps at the neck between two lobes.

## Consequences

- Default results are unchanged: with the share at 0 no depth is computed and the open
  cells are those of before.
- Cost: 4 bytes a lattice cell for the wall distance (one more byte and 4 more bytes a
  cell with a floor), plus the climb. Measured in Nodule's ADR 0018 section 14.
- Tests (`tests/test_volume_dendrites.py`): a side lobe is told from the main one
  (negative control: one ball has no side lobe); a climb does not cross regions; plumes
  stay within a share of the local depth (negative control: share 0, where plume-3d's
  plumes rise farther); with contrast a side lobe fills a smaller share of its depth
  than the main one (negative control: contrast 0, equal shares); the deepest is taken
  on each side of a floor.
- Lattice summits along a narrow ridge can split one lobe into several with nearly
  equal depths; the reach then varies a little along the lobe. Accepted.
