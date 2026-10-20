# 59. A robustness pass: memory, the GPU and settings' limits

- Status: accepted (owner request, 2026-10-18)
- Date: 2026-10-18
- Builds on: [ADR 0054](0054-gpu-by-default-and-progress-for-long-actions.md), [ADR 0057](0057-a-reproducible-gpu-dendrite-engine.md)

## Context

Several recent changes turned up problems that would have hurt users badly,
such as the GPU dendrite engine filling the GPU's memory (ADR 0057). The owner
asked for a thorough pass to bring every status up to date, tidy loose ends
and find such problems before users do. The pass measured the app the way a
long session uses it: heavy 3D builds one after another in one process, as the
server's cache holds them, with the process's and the GPU's memory read after
each; and every model setting pushed to its limits.

## Findings and fixes

1. **Search trees rebuilt on every query.** The dendrite aggregate and the
   chemical-garden tubes built a new k-d tree, and the aggregate a copy of
   every lattice cell's coordinates (720 MB for `moss-fine-3d`), on every
   distance query: each cut, voxel chunk and later stage. Now built once.
   Results bit-identical; `moss-fine-3d` builds in 21 s, from 30.
2. **Whole lattices at once.** The dendrites' open cells and H2's lattice
   were set up from every cell's coordinates and wall tests at once: a peak
   of 3.3 GB of RAM for `moss-fine-3d` and 11.3 GB for `liesegang-nodule-3d`,
   enough to crash many computers (the dendrite budget allowed 128 million
   cells, about 13 GB). Now set up in parts of a million cells: peaks of
   0.8 GB and 3.5 GB, results the same. The dendrite budget is capped at 64
   million cells.
3. **A cached H2 formation held too much.** It kept full-lattice arrays and a
   k-d tree over every inside cell. Now it keeps values for inside cells only
   and looks a point up in its own cell, searching only the rim cells next to
   the wall when its cell's centre is outside. Its own arrays come to about
   0.4–0.5 GB (estimated 0.42, measured 0.49); the whole server process,
   with its libraries and memory freed but not yet returned to Windows, read
   1.6 GB after one H2 build, down from 2.6. A point's own cell is always a nearest one, so values
   change only where a point is exactly equidistant from two cells (248 of
   884,736 voxels of the H2 preset's view; every changed pick checked equally
   near, to 3 × 10⁻¹⁵ mm); a test checks the lookup against a full search.
4. **The GPU's memory kept after a run.** CuPy's pool held 3.6 GB after H2 in
   3D for as long as the app ran, out of reach of other programs. Large runs
   (H2, the dendrite engine) now hand it back (`_rd.release_gpu_memory`).
   Over a session of nine builds the process held a steady 0.7 GB with four
   formations cached: no leak.
5. **H2 crashed in a tiny cavity.** When the reaction front reached every cell
   before its first recorded step, the band assignment indexed below zero
   (an error, in 2D and 3D; it predates this pass). Now one band; a test.
6. **Settings that could crash or stall a run** (every setting of every model
   pushed to its lower and upper limit, from defaults and from every preset):
   - wobble scale near zero asked for 646 PB (the noise lattice is a quarter
     of the scale across, over twice the cavity): with the sliders' 0.05 mm
     and a 150 mm cavity, about 5 GB. Now at least 0.25 mm, below a band's
     width;
   - H1's boundary layer near zero took 11.5 minutes for a small preview. Now
     at least 0.00005 mm (the sliders' lowest; a 256 px preview in 14 s).
   - H2's lattice in 2D had no cap: the sliders' 0.002 mm in a 50 mm cavity
     asks for 600 million cells. It now coarsens beyond 16 million cells (both
     H2 presets keep their lattices exactly);
   - H1's growth history turns stiff past a boundary in rejection and trapping
     velocity (ADR 0060): about 50 s for any preview, over 2 minutes as a
     staged wall, and a single 96 px run grew to 6.8 GB once. It now reports
     progress and stops on Cancel (it reported nothing before, so neither
     could act on it); the caution badge flags it beforehand;
   - also slow but bounded, and flagged by the badge: H4 at 60 pulses with long
     intervals (81 s), 2D dendrites at their finest width (34 s), H2 previews
     at any setting (about 20 s at 96 px: its lattice is set in millimetres).
   Method: from every 2D preset, each numeric setting at its lowest and its
   highest value (or four times its default where unbounded, as the sliders
   allow), each run in its own process with a 2-minute limit and a reading of
   its peak memory (about 2,300 runs).
8. **The 3D cache counted formations, not bytes,** and dropped the oldest
   added, not the least recently used. It now keeps formations up to 1.5 GB of
   their own arrays and search trees (`server/footprint.py`) and at most six,
   least recently used first, always keeping the newest. The budget counts the
   formations, not the whole process (about 0.3 GB of libraries, the 2D cache
   and transient peaks come on top). The 2D preview cache is least recently
   used first too.
9. **In the browser:** the 3D view gives its WebGL context back when the
   screen closes (browsers keep about 16); the animated GIF is drawn twice
   (palette, then frames) and encoded frame by frame, holding one frame instead
   of all (about 240 MB for 20 s), with byte-identical output.
10. **Saved runs** take 2–16 MB each (compressed), but nothing removed them.
    Each run in the 2D and 3D lists now has Delete, with an inline "Delete this
    run? Yes / No"; the server deletes only a run directory directly inside the
    runs folder. Both lists show the runs folder's size.
7. **The Windows start script removed the GPU extra** (`uv sync` without it),
   so a GPU user starting the app that way was back on the CPU without
   knowing. It now keeps an installed GPU extra, takes `-Gpu` to install it,
   and runs with `--no-sync`. The README says how to set the GPU up.

## Status brought up to date

README (status, findings, the GPU, progress and Cancel, layout), glossary
(stick section, length law, dendrite lattice), the app's tour (progress and
Cancel), the gallery (version 25: 3D sheet, stick and dendrite results),
CLAUDE.md (the `--no-sync` rule; how to keep long work cancellable and
memory-safe), roadmap.

## Consequences

- New long loops should report progress, work on large lattices in parts,
  build search trees once and hand GPU memory back (CLAUDE.md).
- A setting's lower and upper limits are part of its definition: the limits
  checked here, not just its default, are what a user can reach.
