# 5. Verification per model tier; parameter natures; exact geometry

- Status: accepted
- Date: 2026-10-15
- Refines: [ADR 0003](0003-model-architecture.md) (item 6) and
  [ADR 0004](0004-archetype-ladder.md)

## Context

M1 delivers the first procedural models. They reproduce fortification, seam and
waterline forms by construction: band position is a direct function of wall
distance or height. If that counted as plain "verified", the ladder would claim
more than the procedural tier shows. It shows the form *can be represented and
measured*, not which conditions or mechanism produce it.

Building M1 also showed that "physical vs effective" (ADR 0003) misses a third
kind of parameter. Procedural models set properties of the result directly,
such as band thickness.

## Decision

1. **Status per tier.** The registry (schema v2) records each archetype's status
   separately for the `procedural` and `mechanistic` tiers. A tier's `verified`
   requires the archetype's dependencies to be verified at that same tier.
2. **Thresholds in the registry.** Each criterion gets a `min` and/or `max`. An
   archetype can't be verified while any of its criteria lacks one. The thresholds
   are the contract; `agatesim.criteria` only measures.
3. **Negative controls.** Each implemented criterion must fail on at least one
   result that lacks its form, and the test suite does this. Example: the
   corner criterion must reject deliberately rounded bands.
4. **Three parameter natures:**
   - `physical`: a measurable environmental condition, such as the gravity
     direction.
   - `effective`: a model coefficient with no direct measurement.
   - `imposed`: a property of the result set directly. Procedural only.
5. **Exact geometry.** Cavity masks and wall distances come from the exact
   polygon (point-in-polygon at the boundary, KD-tree distances to a densely
   sampled wall), not from pixel-based distance transforms. Previews and full
   runs then agree on band identity wherever their pixels coincide (≥ 93% in
   tests; the rest is nearest-pixel sampling at band edges).

## Calibration notes (M1)

- **`corners-preserved`.** The first metric, band spacing along the bisector,
  can't distinguish rounded from sharp bands at obtuse corners: rounding moves
  the corner by only ρ(1/sin(θ/2) − 1), about 0.13ρ at 120°. It was replaced
  before verification by a turn-width metric measured relative to each corner's
  own arms. At 768–1024 px, sharp bands score ≤ 0.37, and rounding by one band
  spacing scores ≥ 1.18, giving a threshold of 0.7. Below 5 px per band the
  criterion reports "too coarse to judge" rather than guessing.
- **`planar`.** Each boundary between bands k and k+1 is fitted on its own. Fitting
  all the edge pixels of band k at once would mix its upper and lower boundaries.

## Consequences

- The README and `docs/archetypes.md` show two status columns. Procedural
  verification is never presented as evidence for a mechanism.
- Changing a verified criterion's threshold now requires an ADR (ADR 0004).
