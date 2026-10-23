# 61. A compiled CPU dendrite engine

- Status: accepted (owner approved Numba as a dependency, 2026-10-23)
- Date: 2026-10-23
- Builds on: [ADR 0056](0056-dendrite-lattice-spacing-is-branch-width.md), [ADR 0057](0057-a-reproducible-gpu-dendrite-engine.md), [ADR 0060](0060-a-caution-badge-for-heavy-actions.md)

## Context

On a computer without a GPU, the 3D dendrites were slow: `moss-fine-3d`'s view
took about 2 minutes, 110 s of it in the aggregation, and `plume-3d`'s
aggregation 8 s of 11. ADR 0056 had suggested jumping walkers across empty
space (3–4 times less work), but that changes every run's dendrites and the GPU
path would have to change with it. The owner asked for faster dendrites on such
computers, with the same results.

Timing each part of the NumPy sweep loop on the presets' own inputs showed
where the time went: about 20 separate passes over every particle per sweep
(hashing 15–26%, choosing and taking the step 30–40%, the touch test 10–14%,
removing stuck particles 18–29%), and on the fine lattice, memory reads
(about 66 ns per particle step). Reusing buffers gained nothing, and threads
helped only on the fine lattice (1.9 times).

## Decision

1. **The CPU loop compiled with Numba** (`agatesim._dla_numba`), Numba a
   dependency (owner approved). The same integer arithmetic as the NumPy loop,
   so the same aggregate, cell for cell and sweep by sweep. Two changes of
   arrangement, neither of which a particle's fate depends on:
   - the lattice's three flags (free, next to the aggregate, in it) share one
     byte per cell, so a step reads memory once;
   - each sweep steps the particles in parallel chunks (a particle's step,
     touch test and sticking draw depend only on its id and the lattice at the
     start of the sweep), and each chunk lists its touching particles, so the
     attaching and removal that follow visit only those (every buried particle
     sits on a cell that just attached, so was touching). Particles are kept in
     no particular order.
2. **The NumPy loop stays** as the reference the compiled loop must match
   (tests on six engine cases: walls, upward bias, the sweep limit, fewer
   particles than chunks, a small budget, nothing attaching), and as the
   fallback when Numba can't be loaded or `AGATESIM_NUMBA=0`.
3. **The GPU path is unchanged** and still takes runs of 100,000 particles or
   more: it remains a little faster there.
4. **One build at a time** through the compiled loop (a lock): Numba's simplest
   threading layer, used where OpenMP and TBB are missing, mustn't be entered
   from two threads at once. Progress is reported every 64 sweeps, so Cancel
   works as before.

## Results

- **Same aggregates:** all five captured preset runs (moss, moss mechanistic,
  moss dense, plume, moss fine) identical to the NumPy loop at 1, 8 and 16
  threads; the GPU path still matches (its test now compares it with the
  compiled loop).
- **Speed** (the aggregation alone; 16 cores):

  | Preset | NumPy | Compiled (1 core) | Compiled (16 cores) | GPU |
  |---|---|---|---|---|
  | moss-3d | 1.9 s | (timed with the first compile) | 0.19 s | (CPU below its threshold) |
  | moss-mechanistic-3d | 1.9 s | 0.95 s | 0.20 s | (CPU) |
  | moss-dense-3d | 2.0 s | 0.59 s | 0.21 s | (CPU) |
  | plume-3d | 8.4 s | 2.3 s | 0.74 s | (CPU) |
  | moss-fine-3d | 110 s | 27 s | 4.4 s (8 cores: 5.7 s) | 3.1 s |

- **Building the 3D view** without a GPU (whole process): `moss-fine-3d`
  19 s (was about 2 minutes), `moss-3d` 4.5 s, `plume-3d` 5.1 s. The rest of a
  build is now mostly setting up the lattice (wall distances, search trees).
- **Compiling** takes 3.6 s once; the result is cached on disk, and later
  processes load it in about 1 s. Memory falls a little: one byte per cell
  instead of three.
- **The caution badge** (`agatesim.estimate`): 3D dendrites now cost a setup
  linear in the lattice's cells (2.2 s + 0.40 µs per cell) plus the
  aggregation at the cells to the power 5/3, compiled (4.5 s at 30 million
  cells on 16 cores, scaled by the cores to the power 0.6), on the GPU (3.1 s)
  or by the NumPy loop (112 s). Estimates against actual: moss-3d view 4.3 and
  4.5 s, moss-fine-3d 18.4 and 19.0 s (it was estimated at 119 s and badged as
  heavy), plume-3d 4.8 and 5.1 s; a full moss run with 40 cuts 62 and 49 s,
  still badged. In a fresh process with a GPU, CuPy's start adds about 3 s
  once.

## Consequences

- No run's result changes; without a GPU, fine dendrites are now ordinary.
- Numba (with llvmlite, about 43 MB) installs with the project.
- The 2D dendrite model is unchanged: it draws from random streams, not hashes,
  so compiling it the same way would change every 2D moss and plume result.
