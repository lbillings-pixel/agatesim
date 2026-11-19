# 90. The crystal wall, returned for rendering, with its closed form for the GPU

- Status: accepted (owner, 2026-11-19 night: approved from Nodule that agatesim return
  the crystal stage's crystals and ship their closed form as a CUDA device function,
  tested against `pair_times`; the shapes below are Claude's choice within that)
- Date: 2026-11-19
- Builds on: [ADR 0023](0023-growth-from-nuclei-in-3d.md) (crystals in 3D),
  [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule needs)
- Spec: Nodule's ADR 0019 s.6.12 (the hollow drawn as air; its probe and the owner's
  choice of an "owner lattice")

## Context

Nodule will render the hollow a geode's quartz leaves as air, with light reflecting
and refracting at the crystal tips. That needs the wall and its normal at any point on
the GPU. Nodule's probe (its ADR 0019 s.6.12, one stone) found a sampled level too
coarse at affordable spacings: a grid rounds each edge between crystals over about a
cell, so only 72-82 % of normals were within 1.5 deg even at 0.025 mm (2.3 GB, ~51
min to fill). Storing instead each lattice node's crystal (0.1-0.2 mm) and evaluating
the earliest of a point's 8 corner crystals in closed form put 98 % of normals within
1.5 deg, with sharp edges. That needs the crystals themselves, which the growth
evaluator kept in a closure (the probe reached them by walking it), and the closed
form on the GPU, which Nodule must not copy (ADR 0072: import, never copy).

## Decision

- **The readout.** `prepare_growth` returns a `GrowthEvaluator`: a callable that is
  the same `Evaluator` as before and carries `crystal_wall`, a `CrystalWall` when the
  run's last stage is quartz crystals (in 3D crystals can only come last, ADR 0023),
  else None. `VolumeSimulation.crystal_wall` reads it (None for other models).
  `CrystalWall` holds the stage's `Crystals`, its last reach (mm) and grain offset, and
  offers `sites`, `axes`, `alpha`, `side_rate`, `times` (= `pair_times`), `arrival`
  (= `assign`: the earliest time and its crystal, as the stage assigns them), `level`
  (arrival − last reach: positive exactly where Fields say VOID) and `packed()` (rows
  of site and axis for the GPU). It is a readout for rendering; criteria never read it
  (they read Fields), and Fields are unchanged.
- **The closed form for the GPU.** `agatesim.volume.crystal_gpu.CRYSTAL_TIME_CUDA` is
  CUDA source with two templated device functions, no kernels:
  `agatesim_crystal_time` and `agatesim_crystal_time_grad` (time and gradient). It is
  a Python string, as `_rd` keeps its kernels, so it travels with a pinned install
  without package data and imports without CuPy. `shape_numbers` gives the two shared
  numbers it takes (cot of the tip half-angle, elongation). Choices within it:
  - *across* is the length of the offset less its part along the axis, not
    sqrt(|offset|² − along²) as in `pair_times`: in float32 at world coordinates the
    latter loses about sqrt(eps)·|offset| (~3 µm at 25 mm) near the axis.
  - The gradient is the closed form's: tip branch sign(along)·axis + cot·(across
    direction), side branch elongation·(across direction). On a tie the tip's is
    returned; on the axis the across term is 0; at along 0 the sign is +.
  - Which crystals a point compares (the owner lattice, the min over its corners) is
    the caller's: Nodule's renderer, not agatesim.
- **Not changed.** `assign`'s candidate jumps (Nodule's probe: late on 4.4 % of wall
  points) and the round-cone tips stay as they are; six-faced tips are a later,
  separately approved change, which would change this closed form here, once.

## Tests (tests/test_crystal_wall.py)

- The level is positive exactly where Fields say VOID, over the points crystals could
  still reach (quartz or hollow) of `quartz-geode-3d`; control: a wall drawn 0.3 mm
  short disagrees. Grains equal the offset plus `arrival`'s crystal, and `times` gives
  `arrival`'s time. A run not ending in crystals (`eye-3d`) has no wall.
- On the GPU (skipped in CI, run here): the device time equals `pair_times` (double
  within 1e-6 mm; float within 2e-5 mm + 5e-7 of the time) on points near a site, far
  away, on the axis and on the tip-side edge; its gradient equals float64 central
  differences of `pair_times` within 1e-5 at smooth points, float within 0.01 deg of
  double there, finite on the axis and the edge. Controls: a tip angle 8 deg wrong, or
  each point tested against the next crystal's row, must not match. The geode's own
  packed wall through the device function equals `arrival`.
- Fields unchanged: `quartz-geode-3d` at 300 000 fixed points hashes the same before and
  after (sha256 5bb88a0e…).

## Measured

On the RTX 4070, 10 M points in float32: the earliest of 8 crystals with the gradient
took 4.1 ms (0.41 ns a point), one trilinear fetch from a 260³ float grid at the same
random points 8.8 ms. Random points are cache-hostile for the grid; a renderer's
coherent rays will fetch faster, and the owner lattice still fetches 8 crystal ids. So a
wall test should cost about one fetch, not 8: GPU time is not the risk the probe
feared. *Plausible* for one card and a synthetic set (11 266 crystals, as the probe's
stone).

## Consequences

- Nodule moves its pin and builds the owner lattice and void box on `crystal_wall`;
  its renderer includes `CRYSTAL_TIME_CUDA` rather than a copy.
- `prepare_growth` returns a `GrowthEvaluator` instance rather than a bare function;
  anything that inspected the closure (Nodule's probe scripts) reads `.evaluate`.
