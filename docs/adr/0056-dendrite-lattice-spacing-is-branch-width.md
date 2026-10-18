# 56. The dendrite lattice's spacing is the branch width

- Status: accepted (owner chose the study and its next step, 2026-10-18)
- Date: 2026-10-18
- Builds on: [ADR 0009](0009-branched-inclusions.md), [ADR 0025](0025-inclusions-in-3d.md)

## Context

ADR 0025 found that the 3D dendrites match Hou et al.'s length law
(N(L) ~ L^-1.25) at a 10% particle concentration, but not their fractal
dimension (2.70–2.80) at the same time [@hou2023]. It suggested a finer
lattice on the GPU. The 3D lattice is coarsened to fit 4 million cells, so the
dendrite width (`dendrite_width_mm`, 0.12 mm by default, the lattice cell)
becomes about 0.23 mm in a 40 mm nodule. Honouring 0.12 mm there takes about
37 million cells, roughly 30 times the work (9 times the cells and particles,
each needing about 3.5 times the steps to reach a branch).

The owner asked whether so much compute is needed, or whether a middle
ground would give comparably better dendrites. The first question was whether
the result depends on the spacing at all.

## The study

`scripts/dendrite_convergence.py` grows a forest up from the floor of a
12 × 12 × 24 mm box, as Hou et al.'s dendrites grow from a fracture surface:
144 seeds 1 mm apart at fixed positions in millimetres, 8% of the open space
in particles, sticking 0.5, the same at every spacing. It measures the box-
counting dimension over the same physical box sizes (0.25–2 mm) and over the
same box sizes in cells (2–16), and the length law over the longer half of the
trees (connected, six-neighbour).

| Concentration | Spacing | Cells | Time (CPU) | Dimension, 0.25–2 mm | Dimension, 2–16 cells | α |
|---|---|---|---|---|---|---|
| 4% | 0.24 mm | 0.28 M | 0.8 s | 1.78 | 2.19 | 1.39 |
| 4% | 0.12 mm | 2.1 M | 13 s | 2.35 | 2.25 | 1.25 |
| 4% | 0.06 mm | 16.4 M | 504 s | 2.63 | 2.32 | 1.25 |
| 10% | 0.24 mm | 0.28 M | 0.6 s | 1.74 | 2.16 | 1.27 |
| 10% | 0.12 mm | 2.1 M | 9 s | 2.36 | 2.26 | 1.25 |
| 10% | 0.06 mm | 16.4 M | 311 s | 2.64 | 2.32 | 1.26 |
| Hou et al. | | | | 2.70–2.80 | | 1.25 |

The tallest trees reach the box's top (24 mm) in every run, so the length law
is cut off at the longest end; the fit uses the longer half of the trees.

## Findings

1. **The spacing is physical, not numerical.** In cell units the forest hardly
   changes with the spacing (dimension 2.19, 2.25, 2.32): the model is close to
   converged as a numerical method. What a finer lattice makes is thinner
   branches, so at a fixed physical scale the forest is more finely divided
   (dimension 1.78, 2.35, 2.63).
2. **The 3D coarsening changes the dendrites.** At the 2D presets' 0.12 mm
   width the length law matches Hou et al. (α = 1.25 at both
   concentrations); at 0.24 mm, about what a 40 mm nodule gets in 3D, it
   doesn't at 4% (1.39).
3. **Finer than 0.12 mm buys little for its cost.** At 0.06 mm the
   millimetre-scale dimension reaches 2.63, near Hou et al.'s 2.70, but the
   length law is unchanged and the run takes about 38 times as long.
4. Particle concentration mattered little in this box, unlike ADR 0025's
   whole-nodule runs (seeds 4 mm apart); the seed spacing probably matters
   more. Left open.

## Decision

1. Aim the 3D dendrites at their intended branch width (0.12 mm), not finer.
2. Before building a faster engine to reach it in whole cavities, measure how
   much of the particles' walking happens far from any branch or wall, which a
   walker could cross in one jump (the usual acceleration of
   diffusion-limited aggregation): that sets the speed-up to expect.
3. Commit the study script, so the study can be repeated.

## Measurement: walking far from the branches

An instrumented copy of the sweep loop, on the box above at 0.12 mm (4%),
recorded every tenth sweep each walker's chessboard distance d (cells) to the
nearest cell where it could stick or be stopped: 6.8 × 10⁸ walker-steps, 5.4%
within a cell of a branch or wall and 47% at 12 cells or more. A walker in a
free cube of half-size d − 1 needs about (d − 1)² steps to leave it, so a jump
to the cube's surface could replace that walking: about 7 times less work.

But every walker moves on one clock while the branches grow, and a branch can
grow a cell per sweep. A jump that skips more sweeps than d − 2 could cross a
branch that grew meanwhile, so an exact jump skips at most d − 2 sweeps: about
3 to 4 times less work, before each jump's own cost. A GPU running the same
synchronous sweeps is the larger lever (estimated 15–30 s for 0.12 mm moss in
a 40 mm nodule, against 10–15 minutes on the CPU now; not yet measured).

## Consequences

- The 3D moss and plume presets keep their coarsened lattice for now; their
  branches are about twice the intended width.
- The dimension Hou et al. report is approached as the branches get thinner
  relative to the scales measured; matching it needs no new physics so far,
  only resolution or a measurement over the matching range of scales.

## Amendment (2026-10-18): the length law doesn't depend on the spacing

Finding 2 rested on one run per spacing. Re-run with the engine of ADR 0057
over four seeds at 4% concentration, the length law's exponent spreads by
about ±0.1 from run to run:

| Spacing | α (seeds 1–4) | Mean | Dimension, 0.25–2 mm |
|---|---|---|---|
| 0.24 mm | 1.13, 1.31, 1.30, 1.26 | 1.25 | 1.75–1.76 |
| 0.12 mm | 1.21, 1.32, 1.33, 1.36 | 1.31 | 2.35 |

So the length law matches Hou et al.'s at both spacings (with seeds 1 mm
apart), and the 1.39 above was one run's scatter. What the coarsening changes
is the dimension at a fixed physical scale, which is steady from run to run;
that is the reason left for the finer lattice.
