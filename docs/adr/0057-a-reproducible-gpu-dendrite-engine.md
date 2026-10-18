# 57. A reproducible dendrite engine for the GPU, and a lattice budget

- Status: accepted (owner approved, 2026-10-18)
- Date: 2026-10-18
- Builds on: [ADR 0025](0025-inclusions-in-3d.md), [ADR 0054](0054-gpu-by-default-and-progress-for-long-actions.md), [ADR 0056](0056-dendrite-lattice-spacing-is-branch-width.md)

## Context

ADR 0056 found that the 3D dendrites' lattice cell is their finest branch
width, that coarsening it to fit 4 million cells doubles that width in a
40 mm nodule, and that the intended 0.12 mm needs about 30 million cells there:
too slow on the CPU, where the aggregation already took seconds at 4 million.
Jumping walkers across empty space would save only 3–4 times while keeping
the result exact; running the same sweeps on the GPU is the larger lever. The
owner approved a GPU engine with a CPU path that gives the same result, a
setting for the lattice's cell budget, a fine moss preset, and the side
effect: every 3D moss and plume run changes (statistically the same forests,
individually different), so their surveys are re-run here.

## Decision

1. **Hashed random numbers** (`agatesim._dla`). A particle's draws are a hash
   (splitmix64) of its id, the sweep and a key from the run's generator,
   instead of draws from a stream. The same integer arithmetic runs in NumPy
   and in a CUDA kernel, and the sticking test compares an exact float64, so
   the CPU and GPU paths grow the same aggregate, cell for cell (a test).
2. **The same algorithm on both.** Synchronous sweeps as before (ADR 0025):
   every particle steps, those touching the aggregate may stick, stuck and
   buried particles leave, and new ones top the concentration up. On the GPU
   a sweep is three fused kernels (step and sticking test; attaching; who
   survives) and one wait for two counts; particles that leave are marked dead
   and compacted now and then, in buffers of fixed capacity (arrays that grew
   each sweep filled the GPU's memory through CuPy's pool). The GPU is used
   from 100,000 particles up, where it is faster; below, a sweep's fixed cost
   outweighs it, and the result is the same either way.
3. **A lattice budget**, `dendrite_cells_3d` (growth model) and `cells_3d`
   (staged model's dendrite stage): the most cells, in millions, the 3D
   inclusions' lattice may have before it coarsens (`effective`; default 4,
   as before). The sweep limit grows with the lattice (40,000 up to the default
   4 million cells, then with the square of the cells across), as a particle
   takes that much longer to diffuse across.
4. **Preset `moss-fine-3d`**: `moss-3d` with a budget of 40 million cells, so
   its branches keep the intended 0.12 mm (29.7 million cells in its nodule).

## Results

- **Same on CPU and GPU**: identical aggregates (cells and attachment order)
  at 0.55 million cells with upward bias and at 4.25 million without, the GPU
  path forced at the smaller size.
- **Speed** (RTX 4070; preparing the formation for the presets):

  | Run | CPU | GPU |
  |---|---|---|
  | 8 mm box, 4.25 M cells, 170,000 particles | 47 s | 5.8 s |
  | moss-3d | 4.9 s (old engine 4.6 s) | 5.4 s |
  | plume-3d (42,000 particles: stays on the CPU) | 11.4 s (old engine 10.7 s) | 11.3 s |
  | moss-fine-3d | 126 s | 39 s |

  Hashing every draw would have made the CPU path twice as slow; spreading
  each particle's id once, choosing the direction by a multiplication rather
  than a remainder, and drawing for sticking only for particles touching the
  aggregate keep it within 10% of the old engine.

- **Against Hou et al.** [@hou2023] (whole-nodule forests grown on their own,
  the measures of ADR 0056):

  | Preset | Cell | Dimension, 0.25–2 mm | Dimension, 2–16 cells | α |
  |---|---|---|---|---|
  | moss-3d | 0.232 mm (4.2 M cells) | 1.79 | 2.20 | 2.72 |
  | moss-fine-3d | 0.120 mm (29.7 M cells) | 2.30 | 2.28 | 3.06 |
  | Hou et al. | | 2.70–2.80 | | 1.25 |

  The fine lattice moves the forest's dimension towards Hou et al.'s. The
  length law does not follow theirs in either: the moss presets start their
  trees 4 mm apart, so neighbours hardly compete for particles, and the
  competition is what gives N(L) ~ L^-1.25. In ADR 0056's box, with seeds 1 mm
  apart, it does (α = 1.25). The seed spacing, not the resolution, decides it.
- **Random cuts** (100 each, 512 px, seed 0), with the new draws:

  | 3D preset | Before (ADR) | Now |
  |---|---|---|
  | moss-3d | 100% (0025) | 100% |
  | moss-mechanistic-3d | 100% (0040) | 100% |
  | plume-3d | 68% (0025) | 70% (anisotropic growth 70%) |
  | plume-mechanistic-3d | 79% (0047) | 79%: its tubes are a chemical garden, not aggregation, so unchanged |
  | moss-fine-3d | — | 98% (fractal dimension 98%) |

## Consequences

- Every 3D moss and plume run differs from before in its details; the 2D
  models are unchanged.
- A fine dendrite run takes under a minute with a GPU (moss-fine-3d, 39 s) and
  about two minutes on the CPU; the progress bar shows the time left. ADR
  0056's estimate of 10–15 minutes on the CPU, extrapolated from a box, was
  pessimistic.
- Matching Hou et al.'s length law in a nodule would need seeds closer than
  the moss presets' 4 mm; a preset for that is left for the owner to decide.
