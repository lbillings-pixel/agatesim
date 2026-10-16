# 27. H2 (Liesegang precipitation) in 3D

- Status: accepted
- Date: 2026-10-16
- Builds on: [ADR 0015](0015-mechanistic-liesegang.md), [ADR 0021](0021-three-dimensional-runs.md), [ADR 0022](0022-corners-at-the-bands-own-corner.md), [ADR 0026](0026-corner-benchmark-from-high-resolution-photos.md)

## Context

In 2D, H2 makes closed, wall-parallel rings, but it rounds fortification's
corners and breaks into spots inward, so it fails the corner test that H1
passes (ADR 0015). The photo benchmark (ADR 0026) found real corners from as
sharp as the photos resolve to moderately rounded, never as rounded as H2's.
The remaining question was whether H2 behaves the same way in 3D, judged on
random cuts like the other 3D models.

## Decision

1. **The same kinetics on six neighbours** (`_rd.liesegang3`). There is a
   fused CUDA kernel on the GPU and a vectorised NumPy path. The two agree to
   1e-16 (a test), and the time step is reduced to 0.15 for stability with six
   neighbours.
2. **A field equation on a fixed lattice** (`agatesim.volume.liesegang`).
   Unlike the other 3D models, H2 is solved once on a cubic lattice. Its
   spacing is fixed in world coordinates, up to 64 million cells. Volumes and
   cuts take each point's value from the nearest lattice cell inside the
   cavity, so cuts at any resolution show the same run. Bands, stain and
   deposition time follow the 2D model.
3. **Preset `liesegang-nodule-3d`**: the flat-faced nodule at 40 mm on a
   0.1 mm lattice, about 38 million cells. It takes about 66 s on the RTX 4070.
   A coarser lattice (0.2 mm) gave only two bands: ring count depends on how
   many cells deep the cavity is.

## Results

- **The configured cut** shows closed, wall-parallel rings that break into
  spots inward, as in 2D. It passes wall-parallel (0.92), closed-bands (0.9)
  and band-count (11). It fails corners-preserved (0.83, with corners at
  0.38–0.83).
- **100 random cuts** (768 px, seed 0):

  | Criterion | H2 in 3D | H1 in 3D (ADR 0022) |
  |---|---|---|
  | all four (fortification) | 0% | 71% |
  | wall-parallel | 54% | 98% |
  | closed-bands | 10% | 100% |
  | band-count | 50% | 100% |
  | corners-preserved | 10% (20 cuts judged) | 71% |
  | corner value where judged, median (quartiles) | 0.66 (0.46–0.78) | 0.38 (0.33–0.52) |

- In 3D, H2 fails fortification for more reasons than in 2D. Most cuts show
  rings broken into spots, too few bands, or bands not following the wall.
  Where corners can be judged, they are rounder than H1's. They are less
  rounded than 2D H2's (1.6–2.4), but at a coarser lattice relative to the
  cavity.
- **Caveat.** Where the rings break up, the spots line up with the lattice
  axes, an anisotropy artefact of the cubic lattice. The breakup itself
  happens in 2D as well, but in 3D the pattern of the spots is partly an
  artefact.

## Consequences

- The corner question now has 2D, 3D and photo evidence pointing the same
  way. Fortification's corners and closed rings are reproduced by growth from
  the walls (H1), not by diffusion-limited precipitation in the cavity (H2).
  That is within the models tested. Real corners also show some rounding,
  which neither model gives in proportion.
- H2's lattice anisotropy could be reduced with a 19- or 27-point Laplacian
  if 3D H2 is studied further (backlog).
