# 32. A front solver for fast fronts

- Status: accepted
- Date: 2026-10-16
- Builds on: [ADR 0028](0028-regularised-h1-at-the-corner.md), [ADR 0030](0030-h1-with-weak-silica-depletion.md)

## Context

The weakly depleted H1 sets of ADR 0030 have switch-like catalysis. In a corner
their front can run several times faster than on a face, and the 2D solver
(`scripts/h1_front_2d.py`) broke down: the impurity layer ahead of a fast front
is thinner than a grid cell, and the quadratic fit that gives the front values
becomes singular. While fixing that, three more faults turned up.

## Decision

1. **Thin boundary layers.** Ahead of a front moving at U, the quasi-steady
   layer decays at m = (U + √(U² + 4))/2 for the impurity and
   (U + √(U² + 4Dε))/(2D) for silica. While m h < 0.35 the grid resolves it and
   the quadratic fit stands. Beyond m h = 0.65 the front value comes from the
   layer's exponential shape, the probe value at 2h as its outside value and
   the flux condition. The layer then travels with the front, and the fluid's
   ghost cells take the outside value. In between, the two are blended.
2. **A race between threads.** Ghost values were written into the field arrays
   while other threads' probes could read them near a sharp tip, so runs
   weren't repeatable. They are now written to separate arrays and copied in
   after the step.
3. **The coverage update** was explicit and overshot when a corner sped up
   suddenly (θ reached 3,400). It is now implicit: stable at any step and
   θ stays in [0, 1].
4. **Robust front law.** Catalysis is written β/(1 + (a_c/a)ⁿ), so a huge
   impurity value can't give ∞/∞. Silica at the front is capped at 1.5 times
   the bulk (it can't physically exceed the bulk by much), so a rare bad fit
   near a tip or the mirror edge can't spike the speed.
5. **Time step and failures.** The step shrinks so the front moves at most 5%
   of a cell per step, and a run whose speed turns invalid or whose step
   collapses stops with the time and place, instead of stalling silently.

## Checks

- **Fast fronts at an imposed speed** (sets 28923 and 43597): front values
  match the exact steady front to four digits at U = 20, 50 and 200, at
  h = 0.2 and 0.1, where the quadratic fit failed. At moderate speeds
  (U = 1–2) the coarse grid (h = 0.2) errs by up to 10–30%; h = 0.1 is within
  0–3%, so these sets are run at h ≤ 0.1.
- **Slow fronts are unchanged in kind and closer to the 1D reference**: the
  straight-front cycle of ADR 0028's set 6 is now period 3.588 and step 0.2746
  (1D: 3.59 and 0.275; before the fixes: 3.646 and 0.2788).
- **Set 28923's straight front** converges to the independent 1D solver from
  the other side: band step 7.66, 6.64 and 6.23 at h = 0.1, 0.05 and 0.025;
  1D 4.60, 5.51, 5.89 and 6.00 at 200–1600 cells; periods 6.02 and 6.04.
- **Repeatable**: an identical corner run now gives bit-identical fronts.
- **ADR 0028's corner, re-run** (set 5, 1.5 γ_c, h = 0.05): lag at t = 150 is
  1.39 (was 1.55), at t = 300 2.73 (was 3.09); thinning toward the corner 0.71
  (was 0.74). At h = 0.025 the lag at t = 150 is 2.31 (was 2.33), so the
  converged value of ADR 0028 is unchanged; only the coarse grid moved. The findings of ADR 0028 stand: the corner lags and
  bands thin toward it, against the photos' 1.02 (ADR 0029).

## Consequences

- The corner of ADR 0030's set 28923 is now settled (see its amendment).
- The solver stays a script. Its 2D results before this ADR (ADR 0028) shift by
  about 10% in the lag, not in kind.
