# 89. A drawn 3D cavity, stored as a level on a lattice

- Status: accepted (owner, 2026-11-18: approved from Nodule, "a general drawn 3D cavity
  (grid-sampled level; SolidConfig option)"; the storage below is Claude's choice within it)
- Date: 2026-11-18
- Builds on: [ADR 0076](0076-changes-for-nodule-n2.md) (level bounds, exact wall distance),
  [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule needs)
- Spec: Nodule's ADR 0018 section 19 (thunder-egg cavities in 3D)

## Context

A 3D run's cavity is a preset solid or a drawn 2D outline extruded into a prism. Nodule
draws thunder-egg stars whose arms are sheets of their own height and lean, so a cut
gains or loses arms with where it falls; a prism shows the same star at every height.
Every consumer uses a cavity only through `Solid` (inside, level, wall distance,
support, level bound), so only `SolidConfig` stands in the way.

Nodule writes each recipe to JSON (sheet logs) and re-validates it often, and
validating a `SolidConfig` builds its solid. So the drawn shape must travel inside the
config, compactly, and building it must be cheap until the solid is queried.

## Decision

`SolidConfig` gains a third shape, `sampled` (`SampledLevel`: lattice shape and
text), beside `preset` and `outline`; it needs a `host`, and `size_mm`, `yaw_deg`,
`pitch_deg` and filaments work as for a drawn outline. Code in
`agatesim.volume.sampled`.

- **Input.** A level on a lattice of equal cubic cells (8-288 nodes a side): positive
  inside, close to the signed distance in cells near the wall. `SampledLevel.of(level)`
  clamps it to ±3 cells, quantises to 8 bits (1/42 cell) and stores it zlib-compressed,
  base64 (at most 4 million characters).
- **The wall** is the zero set of the cubic interpolant of the stored level.
- **Distance.** Built once per cavity on first query (memoised): from every node
  inside or within 3 cells outside, the nearest crossing of the wall on a lattice edge;
  for nodes within 6 cells, the closest wall point (slide along the tangent plane, then
  Newton steps back onto the zero set; a step that leaves the wall is discarded). Every
  accepted point lies on the wall, so no node distance falls short of the true one.
  Outside, the distance is clamped at −3 cells.
- **Queries** read a cubic B-spline over the node distances (approximating, not
  interpolating). Its weights are non-negative and sum to one, so it is smooth (bands
  that follow the wall distance get no kinks) and its slope along an axis is at most
  the largest neighbouring difference: `level_bound` reports √(Σ of those squared),
  about √3, with no error term. `wall_distance` is max(level, 0); `contains` is
  level > 0; `support` comes from the wall's edge crossings.
- **Scale.** The cavity is scaled so its longest side (from the crossings) is `size_mm`
  and centred on the origin, as presets are. The lattice belongs to the drawing, not
  to the run, so previews, full runs and slices at any resolution read the same
  function.
- **Refused** (each a negative control in `tests/test_sampled.py`): a bare
  inside/outside mask (more than 1 % of wall-crossing edges with |level| summed over
  2 cells: a terraced wall), a cavity in several pieces, one within 2 nodes of the
  lattice's border, an empty one, a lattice too small or large, unreadable text.

## Results (this PC, CPU, 2026-11-18)

| Case | Stored | First query | Query | Error against exact |
|---|---|---|---|---|
| Ellipsoid 40×28×18 mm, 0.4 mm cells | 93 kB | 3.5 s | 0.26 s per 10⁶ points | mean 4.0 µm, 95 % within 7.4 µm, max 0.13 mm |
| Same, 0.8 mm cells | 18 kB | 0.8 s | 0.23 s per 10⁶ | mean 22 µm, 95 % within 57 µm |
| Star (sphere union, arms 0.5-1.6 mm thick), 0.2 mm cells | 403 kB | about 20 s (a draft refining every node) | 0.30 s per 10⁶ | mean 5 µm, 95 % within 21 µm, max 0.14 mm (thinnest arm tips) |

The largest errors sit on the medial ridge, where the exact distance has a crease
that the B-spline rounds over about a cell; at a sphere's centre (a cone's apex) the
rounding is about a cell (14.05 mm for 15 mm, 1 mm cells). Along lines through the
cavity the slope changes smoothly: 99th percentile of its change per 0.02 mm step
0.022 (exact 0.007; across the ridge the exact distance jumps by 1.04, this by at most
0.073). A distance to the nearest of a set of wall samples would jump by about 0.5.
Validation costs 0.01-0.05 s for these lattices (decompress, check); configs repeat
it cheaply because the built solid is memoised by its stored text.

## Consequences

- Nodule can draw thunder-egg cavities in 3D (its item 17) and any other cavity a
  preset cannot give, without agatesim knowing how they were drawn.
- Recipes with a drawn 3D cavity are larger (tens to hundreds of kB of text).
- The distance build costs seconds to tens of seconds per cavity per process, once.
  A faster build (compiled loop) can follow if Nodule's sheets show it matters.
- Not offered in the web app: there is no 3D drawing tool.

## Alternatives considered

- **Store a path to a file.** Rejected: sheet logs and CI would depend on files kept
  beside the recipe.
- **Rebuild the shape from a seed inside agatesim.** Rejected: the drawing is
  Nodule's, tuned by its owner's eye; moving it here would tie every look change to a
  library change.
- **A union of primitives (spheres, hulls).** Exact distances need seam handling
  (ADR 0076 s.5) that grows with the number of pieces, and a winding arm needs
  thousands of spheres.
- **Distance transform of an inside/outside mask, read trilinearly.** Stair-stepped
  walls and kinks in the slope, which finite-difference gradients (channels, folds,
  Nodule's rind) and wall-following bands would show; refused at input instead.
