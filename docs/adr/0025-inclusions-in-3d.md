# 25. Filaments and branched inclusions in 3D

- Status: accepted
- Date: 2026-10-16
- Builds on: [ADR 0009](0009-branched-inclusions.md), [ADR 0023](0023-growth-from-nuclei-in-3d.md)

## Context

After ADR 0023, the formation forms still missing from 3D were tube, moss and
plume agate. The literature already read gives 3D facts to aim at:

- **Filaments.** Götze et al. [@goetze2020b] (sections read) describe
  filaments in basalt cavities: on the ceiling and walls partly elongated
  downward by gravity (pseudo-stalactites), and randomly intergrown on the
  floor, embedded in chalcedony like moss agate.
- **Dendrites.** Hou et al. [@hou2023] (read in full) describe 3D Mn-oxide
  dendrite forests grown by attachment of diffusing particles. Their 3D
  fractal dimension is about 2.70–2.80. Dendrite numbers fall with length as
  N(L) ~ L^-1.25, and higher concentrations give bulkier dendrites.

## Decision

1. **Filaments** are straight segments with a radius (`solid.filaments`). The
   growth model treats them as solid surfaces that later growth lines, like
   the wall, and they stay exact pieces of the solid. They are only
   available with the growth model, as in 2D. Preset `tube-3d`: four filaments
   hanging from the roof, with the 2D tube preset's positions and radii.
2. **Branched inclusions** grow by multi-particle diffusion-limited
   aggregation on a cubic lattice (`agatesim.volume.dendrites`), the 3D form of
   the 2D model (ADR 0009). It has six-neighbour walks, the same particle
   concentration, budget and sticking, the same upward bias for plumes, and
   seeds from sites on the growth surface. The lattice has a fixed cell size
   in world coordinates, coarsened to 4 million cells (0.23 mm in a 40 mm
   nodule). Each aggregated cell is drawn as a ball of 0.8 cell sizes, moved
   by a fixed pseudo-random offset of up to 0.2 cell sizes. That makes
   branches rounded, connected strands in a cut, not a pattern of lattice
   cubes. The aggregate is a piece of the solid that later stages line.
3. **Presets** `moss-3d` and `plume-3d` use the 2D verification presets'
   settings.

## Results

- **Configured cuts pass**: tube across the filaments (seed-concentric 0.98),
  moss (dimension 1.53, inclusions 12% of the cavity) and plume (alignment
  0.90, all enclosed). Along a filament, a cut shows it as a stripe with bands
  parallel to it that wrap round its free tip.
- **Random cuts** (100 each, 512 px, seed 0):

  | 3D preset | Cuts passing | Depends on |
  |---|---|---|
  | moss-3d | 100% | — |
  | plume-3d | 68% | gravity in the cut: 100% when ≥ 0.9, 57% at 0.5–0.9, 0% below 0.5 |
  | tube-3d | 11% | angle between the cut's normal and the filaments: 11 of 13 within 30°, 0 of 87 beyond |

  - **Tube.** Ring systems appear only on cuts within about 30° of square-on
    to the filaments. Beyond that the rings stretch into ellipses and
    stripes. The 2D criterion is meant for filaments "seen end-on", so this
    is the expected limit, not a flaw.
  - **Plume.** Rising branches show as rising only on cuts that contain the
    vertical.
- **Against Hou et al.**, from the moss preset's aggregate:

  | Particle concentration | 3D fractal dimension | Length law N(L) ~ L^-α |
  |---|---|---|
  | 4% (the 2D-calibrated preset) | 1.95 | α = 1.57 |
  | 10% | 2.2 | α = 1.21 (Hou et al.: 1.25) |
  | 20–30% | 2.65–2.68, but the trees merge into one network | — |
  | Hou et al. | 2.70–2.80 | 1.25 |

  The length law matches Hou et al. at a 10% concentration. Their dimension
  is approached only where the dendrites merge. So, at this lattice
  resolution, the model doesn't reproduce both observations at once. The
  presets keep the 2D-calibrated concentration, which passes the moss
  criteria. At 10% the moss criteria pass too, but a cut shows mainly
  isolated specks. Box counting on trees a few tens of cells across also
  reads low, so the dimensions above are lower bounds.

## Consequences

- Ten of the twelve archetypes now run in 3D: fortification, seam, waterline,
  combined, quartz geode, botryoidal, eye, tube, moss and plume. The other
  two, shadow and iris, are optical views of a cut, which the optical
  renderer can already give for any 3D cut.
- Matching Hou et al.'s dimension and length law together probably needs a
  finer lattice (on the GPU) or a different aggregation model, such as their
  lattice-Boltzmann reaction–diffusion–aggregation model. Recorded as backlog.
