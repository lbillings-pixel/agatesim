# 47. Plume and the mechanistic geode in 3D

- Status: accepted
- Date: 2026-10-17
- Builds on: [ADR 0040](0040-mechanistic-forms-in-3d.md), [ADR 0044](0044-plume-agate-as-a-silica-garden.md), [ADR 0046](0046-a-geode-that-bands-while-open.md)

## Context

Two mechanistic forms had no 3D version: plume agate, because the 3D
staged model rejected its chemical-garden stage, and the quartz-centre geode,
because H1's quartz in 3D had no crystals, so `inward-coarsening` couldn't be
judged on cuts. Both 3D presets stayed procedural.

## Decision

1. **A garden stage in 3D** (`agatesim.volume.gardens`), the same growth as
   in 2D (ADR 0044) with 3D directions:
   - seeds are sites on the growth surface (from the fixed reference
     lattice, as for every 3D stage) whose inward normal is within 60° of up;
   - a tip turns toward vertical by buoyancy × step × its angle from
     vertical, and wanders in both directions across its direction; a side
     tube leaves at 35° in a random direction about the tube;
   - a seed's solution builds the same length of tube as in 2D;
   - tubes stop at the wall (checked exactly against the solid) or at another
     seed's tube, and are kept as segments, a piece of the exact solid that
     later stages grow from, like branched inclusions (ADR 0040).
2. **Linking assumption:** tubes are drawn at least 0.2 mm in radius in 3D
   (the 2D preset's 0.06 mm), so voxels and cuts at the usual resolutions
   resolve them, as branched inclusions are drawn as balls a lattice cell
   wide (ADR 0025). The length a seed builds is unchanged.
3. **Crystals in 3D H1's quartz**, as in 2D (ADR 0037): sites on the
   chalcedony's inner surface (the wall offset by the depth where quartz
   starts), prism growth forms, geometric selection propagated inward over
   the reference lattice (the growth model's `Crystals`, ADR 0023). H1's
   history says when quartz reaches a point, the crystals which crystal fills
   it. Lining growth only; runs without quartz are unchanged.
4. **Presets** `plume-mechanistic-3d` (the procedural 3D plume's cavity and
   seed, order `garden-wall`) and `quartz-geode-mechanistic-3d` (the 2D
   preset's settings, ADR 0046, in the procedural 3D geode's almond).

## Results

- **Configured cuts** (512 px): `plume-mechanistic-3d` passes (anisotropic
  growth 0.94, encapsulated 1.0); `quartz-geode-mechanistic-3d` passes (no
  quartz touches the wall, 416 crystals widening inward, Spearman 0.88,
  quartz last).
- **Random cuts** (100 each, the same survey settings as the procedural
  presets' recorded rates, which it reproduces):

  | Preset | Pass rate | Weakest test |
  |---|---|---|
  | plume-mechanistic-3d | 79% | anisotropic growth 79%, encapsulated 95% |
  | plume-3d (procedural) | 68% | anisotropic growth 68% |
  | quartz-geode-mechanistic-3d | 77% | inward coarsening 77%, others 98% |
  | quartz-geode-3d (procedural) | 76% | inward coarsening 76%, others 94% |

- **The geode's bands**: 8 in 3D (2 if closed from the start), the last
  3.9 mm from the wall.
- **Garden growth** in the plume cavity: about 56,000 segments in 10 s
  (tips recheck the wall only when their clearance, which falls by at most
  a step per step, could have run out). With buoyancy the mean |cosine| of the
  segments' angle to vertical is 0.94; without it, and with more wander, it
  falls below 0.7 (a test).
- **Volume**: in the plume, H1 grows after the tubes and fills the rest
  (a test); in the geode, crystals fill exactly H1's quartz and those that
  reach deeper are bigger, counted by volume from random points (a test).
- Every other 3D preset is unchanged: the fields of all 16 hash
  bit-identical before and after (the H2 nodule skipped: it needs the GPU).
  The garden stage is new, and crystals are added only where H1 grows
  quartz, which no other preset does.

## Consequences

- Every form verified at the mechanistic tier now has a mechanistic 3D
  version except iris (a thin slice's optics) and shadow (pending).
- The geode closes at 0.6 of the cavity by volume in 3D, which is reached
  nearer the wall than 0.6 by area in a slab, so its banded rim is thinner
  than in 2D.
