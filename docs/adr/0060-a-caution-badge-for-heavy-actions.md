# 60. A caution badge for heavy actions

- Status: accepted (owner request and thresholds, 2026-10-18)
- Date: 2026-10-20
- Builds on: [ADR 0054](0054-gpu-by-default-and-progress-for-long-actions.md), [ADR 0059](0059-a-robustness-pass.md)

## Context

Progress bars (ADR 0054) say how long an action has left once it runs; nothing
said beforehand that an action would be heavy, except H2's model title without
a GPU. The robustness pass (ADR 0059) found many ways to start one: H1 at high
rejection or trapping velocity, H2 at fine lattices or without a GPU, fine 3D
dendrites, full runs at the largest sizes, long surveys, many settling pulses.
The owner asked for a caution indicator on actions estimated to take more than
30 seconds or 2 GB of memory, and for the tour to show it.

## Decision

1. **An estimate before each heavy-capable action** (`agatesim.estimate`):
   rough time and peak memory, with the main reasons, from what was measured
   to drive cost, all instant to compute. `POST /api/estimate` (the 2D preview
   and a full run) and `POST /api/volume/estimate` (building the 3D view, a
   survey, a full 3D run, at the resolutions the app would use; a formation
   already prepared costs nothing to build again).
2. **The cost model:**
   - pixels (2D: simulating, rendering and judging) and voxels (3D);
   - H1: a sharp switch from about 1 s to about 55 s where its rhythm turns
     stiff, above a trapping velocity that falls as rejection rises (always at
     rejection 2 and above), measured on a grid of 64 settings and drawn on the
     cautious side; longer with a thinner boundary layer;
   - H2: lattice cells (capped, ADR 0059) to the power 5/3, ×70 without a GPU;
   - dendrites: lattice cells (2D, and 3D within its budget), on the GPU above
     its particle threshold, slower with the plume's upward bias;
   - H4: pulses × their interval (not the resolution);
   - surveys: cuts × cut pixels; stick agate's tests take 3.7 times a cut's
     usual, and moss (2.8), botryoidal (2.0) and plume (1.8) cuts search
     dendrites or spheres.
3. **The badge** (`CautionBadge`): amber, "Heavy: about 2 min · about 3.4 GB
   of memory" (memory named when it is 1 GB or more), beside the action: the
   2D preview's status and "Run full resolution"; the 3D screen's toolbar (the
   view builds by itself), "Survey random cuts" and "Save a full 3D run".
   Hovering or focusing it gives the reasons. Nothing shows for light actions.
4. **The tour** gains a "Heavy work" step with an example badge beside a
   button, and how progress and Cancel follow.

## Results

Measured with `scripts/calibrate_estimates.py` (24 scenarios, each in its
own process) after tuning:

| Action | Actual | Estimate | Badge |
|---|---|---|---|
| 2D full runs, 1024–2048 px (fortification, stick, eye, fortification mechanistic) | 3–18 s, 0.5–1.4 GB | 3–14 s, 0.6–1.0 GB | none |
| 2D moss, 2048 px | 24 s | 13 s | none |
| H1 stiff (rejection 2–5, or trapping velocity 2.3–3.1), 256 px | 41–46 s, 1.2–1.3 GB | 55 s, 0.4 GB | shown (all 7) |
| H1 below its boundary (trapping velocity 1.5) | 0.7 s | 1.2 s | none |
| H2 2D nodule, 512 px; at lattice 0.035 mm | 14 s; 53 s | 14 s; 44 s | none; shown |
| 3D views: moss, moss fine, plume | 6–19 s | 5–15 s | none |
| 3D view: H2 nodule | 92 s, 2.9 GB | 97 s, 2.9 GB | shown |
| Survey: 40 fortification cuts at 512 px; 20 stick cuts at 768 px | 19 s; 83 s | 21 s; 84 s | none; shown |
| Full 3D run: fortification at 256³ | 5.8 s, 1.25 GB | 6.9 s, 1.24 GB | none |
| Full 3D run: moss at 192³ with 40 cuts | 51 s | 27 s, now 63 s | missed, now shown |

Every action over 30 s or 2 GB was flagged except the last: a moss cut takes
twice an ordinary cut (0.47 s at 512 px), moss fine's nearly three times,
botryoidal's and plume's about twice, so those factors were added. H1's stiff
memory is under-estimated (1.3 GB against 0.4) but stays well under 2 GB. The
2D moss run is the largest remaining under-estimate (about 2×), below 30 s.

## Consequences

- When a model's cost changes (a new solver, a new stage), its estimate needs
  re-measuring: `scripts/calibrate_estimates.py` runs the scenarios above and
  prints each beside its estimate; the constants live in `agatesim.estimate`.
- The estimates are for this machine (RTX 4070, 16 cores); slower computers
  take longer, but the badge still marks the actions that are heavy anywhere.
