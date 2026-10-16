# 22. The corner test looks for each band's own corner

- Status: accepted (owner approved, 2026-10-16)
- Date: 2026-10-16
- Amends: the `corners-preserved` criterion of the fortification archetype ([ADR 0005](0005-verification-tiers-and-parameter-natures.md))
- Builds on: [ADR 0021](0021-three-dimensional-runs.md)

## Context

`corners-preserved` measures how sharply each band near a wall corner turns.
For band k it takes the point where the wall corner's bisector crosses the
band. It measures the turn within two band spacings of that point and scores
the width of the turn over the band spacing (pass at most 0.7).

The test assumes the band's corner lies on the bisector. That is exact in 2D,
where bands at a fixed depth from the wall are offset curves of the outline.
It is wrong on most cuts through a 3D nodule (ADR 0021). Each face of a
flat-faced nodule meets the cut at its own angle, so its bands advance across
the cut at their own apparent rate, 1/sin of that angle. A band's corner then
drifts along the band, away from the bisector.

On 100 random cuts through the 3D fortification presets, the bands stay
perfectly sharp; they are cross-sections of offset polyhedra. Yet the test
passed only 30% (procedural) and 24% (H1) of cuts. Profiles of the band
direction showed a clean step of the wall corner's turn, 2–4 band spacings off
the bisector. A collector judges fortification on whatever cut the saw made,
so the old test would reject many real fortification agates.

## Decision

1. For each band, the turn is first measured at the bisector point, exactly
   as before.
2. If the turn there is wider than 0.35 band spacings, or can't be measured,
   the test also looks for the band's own corner. That is the point within 4
   band spacings along the band where the band's direction is halfway through
   its turn. The turn is measured there by the same method, and the sharper of
   the two measurements counts.
3. Everything else is unchanged: the threshold (0.7), the bands probed, the
   5 px minimum spacing, and the turn measured against the wall corner's
   angle.

A band whose corner is rounded is wide wherever it is measured, so rounded
bands still fail. The new search can only lower a band's score, so the 2D
verifications are unaffected.

## Results

- **2D verification presets score exactly as before**: fortification 0.37,
  fortification-mechanistic 0.45. The combined and waterline presets have no
  corners. The full test suite passes.
- **Negative controls still fail**: bands rounded with `corner_rounding_mm =
  1` score 2.08, unchanged. H2's Liesegang rings still score above 1.
- **3D random cuts** (100 cuts each at 768 px, seed 0):

  | 3D preset | Cuts passing, old test | Cuts passing, new test |
  |---|---|---|
  | fortification-3d (procedural) | 30% | 76% |
  | fortification-mechanistic-3d (H1) | 24% | 71% |

  The remaining failures are cuts the test can't judge, either with too few
  bands near a corner or bands under 5 px apart (8–9%). The rest are corners
  whose band turns over a width beyond the threshold (9–12%), or whose band
  corner lies more than 4 spacings away (2–11%). The latter happen mostly where
  faces lying outside the plane merge or split the cut's corners.

## Consequences

- Fortification's procedural and mechanistic verifications stand. Their
  presets pass with the same values.
- The test now matches what a cut face shows. That matters for photos
  (M10), which are always cuts.
