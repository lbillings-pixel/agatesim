# 30. H1 with weak silica depletion

- Status: accepted (exploratory; the corner is not settled)
- Date: 2026-10-16
- Builds on: [ADR 0017](0017-h1-without-the-boundary-layer.md), [ADR 0028](0028-regularised-h1-at-the-corner.md), [ADR 0029](0029-bands-toward-corners-in-real-agates.md)

## Context

In every oscillating set of ADR 0028, silica at the front is depleted to 14–31%
of the bulk. That supply limit is what makes the corner lag: a corner is fed
from less fluid than a face. The photos favour corners that keep up
(ADR 0029). So: can H1 with a surface state oscillate while silica is barely
depleted? If it can, would its corners keep up?

## Decision

- `scripts/h1_surface_stability.py --q-range LO HI` draws the silica uptake q
  from a narrower range, and hits print their front silica s_f. A scan of
  50,000 sets (seed 2) with q from 0.001 to 0.1 replaced the default 0.1–10.
- `scripts/h1_front_2d.py` now shrinks the time step whenever the front speeds
  up, so it never moves more than 5% of a cell per step. Runs with slow fronts,
  including all those of ADR 0028, keep the old step.

## Results

### Oscillation with weak depletion exists

- **7 of 50,000 sets** have an oscillatory instability, with s_f from 0.92 to
  0.999: silica at the front is 92–99.9% of the bulk.
- In the independent 1D front-frame solver, **two settle into limit cycles that
  hold on finer grids**: set 28923 (s_f 0.99; period 6.0, band step 5.9
  screening lengths, speed swinging 0.23–3.1) and set 43597 (s_f 0.92; period
  0.38, step 1.1). The other five fall to a steady front or stall.
- **No smoothing is needed.** The exact ripple analysis finds no stationary
  instability at any wavelength in either set, and short ripples decay: the
  ripple growth of ADR 0017 came from the silica field, which is now nearly
  uniform. Long oscillatory ripples still grow, faster than the uniform rhythm
  in set 28923 (0.94 at k ≈ 1 against 0.64).
- Both cycling sets have strong, switch-like catalysis (β = 222 and 52, n = 8).

### The corner is not settled

- In a 2D corner (set 28923, a quarter of a cavity 240 screening lengths
  across), the corner runs ahead of the faces within the first few bands,
  while the bands along the faces stay parallel and even. The likely reason:
  impurity rejected from two walls piles up in the corner and switches the
  catalysis on. The time step then shrinks sharply, so the front speeds up
  there by a large factor (not measured directly).
- The solver can't follow that. At such speeds the impurity layer ahead of the
  front is thinner than a grid cell, and the fit that gives the front values
  becomes singular where (1 − K) U h approaches 0.83. Two grids give opposite
  outcomes (the whole cavity filling fast with no bands at h = 0.2; the faces
  freezing at h = 0.1). Neither is trustworthy.
- Set 43597's corner run at h = 0.1 didn't finish in over 30 minutes and was
  stopped: its time step shrank to follow very fast growth. That fits the same
  corner runaway, but doesn't show it.

## Consequences

- H1's rhythm doesn't need a starved front: weakly depleted fronts oscillate,
  and their fronts are smooth without extra assumptions. That removes the
  structural reason for corner lag found in ADR 0028.
- But these sets are switch-like, and a corner's extra impurity can flip them
  into runaway growth. Whether the corner then keeps up, runs ahead, or ends
  the banding needs a solver that resolves thin, fast boundary layers
  (adaptive refinement near the front, or an exponential rather than quadratic
  front fit).
- Backlog: that solver; a scan for weakly depleted cycles with gentler
  catalysis (smaller n), which would be easier to resolve and less likely to
  run away in a corner.
- The owner asked whether pressure in the cavity matters. None of the
  mechanistic models has pressure: the fluid is still, at fixed temperature
  and pressure. Pressure swings that pump or stir the cavity fluid would keep
  it well mixed, which is the condition under which corners keep up. A quick
  search found agate formation still debated between open (pulsed inflow) and
  closed systems, and no study testing pressure-driven mixing. Open idea,
  untested.
