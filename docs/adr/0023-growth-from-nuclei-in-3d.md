# 23. Growth from nuclei and quartz crystals in 3D

- Status: accepted
- Date: 2026-10-16
- Builds on: [ADR 0007](0007-formation-history-and-growth-model.md), [ADR 0008](0008-drawn-cavities-nucleation-and-crystal-growth.md), [ADR 0021](0021-three-dimensional-runs.md)

## Context

M9 (ADR 0021) brought the distance- and height-based models to 3D. The forms
that grow from points were left in 2D: botryoidal and eye agate from
nucleation sites, and the quartz-centre geode's crystals.

A 3D test of eye agate is the obvious next question. The archetype registry
describes eyes as "half-ring systems rooted on the wall" in a cross-section,
and as "circles" on a surface ground parallel to the wall.

The literature pass found no peer-reviewed study of eye geometry.
Götze et al. [@goetze2020] (sections read) describe banding that starts as
separate spherulites on the wall and continues inward as fibrous layers (their
Fig. 29). They also read botryoidal textures as precipitation of silica gel in
free space. That eyes are hemispherical spherulites seen in section appears
only in hobby sources. The 3D tests below therefore check consequences of the
model, not established facts.

## Decision

1. **The procedural growth model runs in 3D** (`agatesim.volume.growth`). It
   has the same stages as in 2D: lining, spherulites from sites, quartz
   crystals from sites, and settling. It uses the same schedules, bands, iron
   and micro-banding, from the same random streams.
2. **The solid after each stage stays exact.** It is a union of the wall
   offset by the lining grown so far, the spherulites as balls, and the
   settled bed as a half-space. Lining offsets every piece by its thickness.
   The distance to the solid at any stage is the smallest distance to a
   piece, so the model is evaluated at any point, as the M9 models are.
   Crystals end the chain, and dendrites are not in 3D yet. Configurations that
   need either are rejected with a message.
3. **Sites on the growth surface** are drawn around the fixed reference
   lattice, projected onto the surface and accepted with blue-noise spacing, as
   in 2D, so they don't depend on resolution.
4. **Which site wins.** Site ownership is propagated inward over the
   reference lattice, shell by shell. A crystal that outgrows its neighbours
   therefore keeps winning however far it reaches from its own site. A point
   compares the owners of the lattice nodes around it and its nearest sites.
5. **Presets** `eye-3d`, `botryoidal-3d` and `quartz-geode-3d` use the 2D
   verification presets' settings in 3D cavities.

## Results

- **The configured cuts pass**, through the middle of each cavity, for eye
  and botryoidal agate (eye: 6 centres, 5 on the wall; botryoidal: 12–16
  lobes). The geode's cut passes phase-transition and quartz-last but fails
  inward-coarsening (0.2 against 0.5).
- **Eyes become circles near the wall.** Horizontal cuts were moved up the
  eye vesicle toward its top wall (half-height 20 mm). The share of growth
  centres on the cut's outline falls from 71% at the middle to 29–50% at
  8–17 mm, and to 0 from 18 mm. There one or two eyes remain as closed
  bullseyes inside the cut (`docs/images/volume.png`). That is the registry's
  "circles on a surface ground parallel to the wall", reproduced as a
  consequence of the model.
- **Random cuts** (100 each, 512 px, seed 0):

  | 3D preset | Cuts passing | Failing criterion |
  |---|---|---|
  | botryoidal-3d | 98% | — |
  | eye-3d | 11% | wall-nucleated (11% pass); discrete and isolated eyes 100% |
  | quartz-geode-3d | 7% | inward-coarsening (7%); 6% of cuts miss the quartz |

  - A cut shows an eye rooted on the wall only if it passes near the eye's
    nucleation site. Elsewhere the eye's rings are centred away from the
    cut's outline, as on the cut near the wall.
  - **Quartz coarsens inward in 3D as strongly as in 2D.** Counting each
    crystal's volume from 1.5 million random points gives a Spearman
    correlation of 0.86 between crystal depth and size (2D: 0.94). A cut
    gives only 0.2–0.3. A cut slices each crystal at a random place, and it
    cuts the deepest crystals through their pointed tips. Even so, the upper
    envelope of section size still grows inward (90th percentile 0.5 to
    1.35 mm), except at the tips.

## Consequences

- All twelve forms except moss, plume, tube, shadow and iris now run in 3D.
  Dendrites and tubes need their own 3D growth. Shadow and iris are optical
  views of a cut, which 3D results already provide.
- Two 2D criteria assume the cut passes through the structure they judge, as
  the corner test did before ADR 0022:
  - `wall-nucleated` (eye) assumes the cut passes through the eyes'
    nucleation sites;
  - `inward-coarsening` (geode) assumes the cut runs along the crystals.

  Changing either needs an ADR and the owner's approval; both are proposed at
  the M11 check-in.
