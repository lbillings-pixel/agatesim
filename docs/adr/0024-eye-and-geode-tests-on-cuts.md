# 24. Eye and geode tests that survive the cut

- Status: accepted (owner approved, 2026-10-16)
- Date: 2026-10-16
- Amends: `wall-nucleated` (eye) and `inward-coarsening` (quartz-centre geode)
- Builds on: [ADR 0022](0022-corners-at-the-bands-own-corner.md), [ADR 0023](0023-growth-from-nuclei-in-3d.md)

## Context

ADR 0023 found two 2D criteria that assume the cut passes through, or along,
the structure they judge, as the corner test did before ADR 0022.

- **`wall-nucleated`** counted only growth centres on the cavity wall. A cut
  shows an eye rooted on the wall only if it passes near the eye's nucleation
  site. Just inside the wall, the same eye is a closed bullseye. The archetype's
  own summary describes those as eyes ("circles on a surface ground parallel
  to the wall"). Only 11% of random cuts through `eye-3d` passed.
- **`inward-coarsening`** correlated each crystal section's mean depth with its
  size. In 3D the crystals do coarsen inward: a Spearman correlation of 0.86
  between crystal depth and volume, against 0.94 in 2D. But a cut slices each
  crystal at a random place and cuts the deepest through their pointed tips,
  so the statistic gave 0.2–0.3. Only 7% of random cuts through
  `quartz-geode-3d` passed.

## Decision

1. **`wall-nucleated`**: a growth centre counts as an eye rooted at the wall if
   either:
   - it lies on the cavity wall, as before; or
   - its rings are closed around it, covering at least 75% of 24 directions,
     with no seed (inclusion phase) within half its curvature radius.

   Rings closed around a seed are tube agate, not eyes, so the tube negative
   control still fails. Threshold unchanged (0.8).
2. **`inward-coarsening`**: the Spearman correlation between depth into the
   quartz and the mean crystal width there. The width at a depth is the length
   of the curve of equal wall distance through the quartz, divided by the
   number of crystals it crosses. It is taken at 10 depths over the outer 80%
   of the quartz layer; the deepest fifth is left out because an oblique cut
   shows crystal tips there. "Fewer, wider crystals inward" is what geometric
   selection leaves, and it holds on any cut. Threshold unchanged (0.5).

## Results

- **2D verification presets still pass.** Eye: wall-nucleated 1.0, unchanged
  (all 6 centres on the wall). Geode: inward-coarsening 0.99 (was 0.94); the
  mean crystal width grows from 0.55 to 0.86 mm inward.
- **Negative controls still fail.** Tube agate scores 0 on wall-nucleated
  (each closed ring has a seed). Fortification has no growth centres. Crystals
  of one size scattered at random score −0.22 on inward-coarsening.
- **3D random cuts** (100 each, 512 px, seed 0):

  | 3D preset | Old tests | New tests |
  |---|---|---|
  | eye-3d | 11% | 30% |
  | quartz-geode-3d | 7% | 76% |

  - **Geode.** The remaining failures are mostly the 6% of cuts that miss the
    quartz.
  - **Eye.** Most remaining failures are cuts partway between the middle and
    the wall. They slice an eye's dome off-centre, so its rings are arcs
    centred near, but not on, the cut's outline. Counting those too would
    need a rule for when an arc system reaches the wall. That is a further
    decision, not made here.
- A cut just inside the wall of `eye-3d` now passes as eye agate (test).
