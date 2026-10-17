# 43. A fast rhythm for iris agate

- Status: accepted (iris stays pending at the mechanistic tier; see Consequences)
- Date: 2026-10-17
- Builds on: [ADR 0010](0010-optical-renderer.md), [ADR 0013](0013-mechanistic-front-feedback.md), [ADR 0041](0041-reading-for-shadow-iris-and-plume.md), [ADR 0042](0042-iris-spacing-from-measured-gratings.md)

## Context

Iris agate's colours come from a grating of thin lamellae, 1.7–64 µm apart,
at right angles to the chalcedony fibres. They are found only in pure,
colourless chalcedony, and in Jones's opinion formed while the fibres grew,
by rhythmic crystallisation, with the spacing perhaps varying with the rate of
crystallisation ([@jones1952], ADR 0041). The procedural model imposes the
micro-band spacing.

## Decision

1. **`micro_rhythm`** (on/off) for H1, with one `effective` parameter,
   `micro_boundary_layer_um` (δ_m, default 0.1 µm). The same feedback is taken
   to run a second time at a much thinner boundary layer, as a fast rhythm.
   - In H1's dimensionless units a cycle takes the same time T in either layer
     (T is measured from the visible rhythm: the median time between speed
     maxima), but the time unit scales with the layer's thickness squared
     (δ²/D against δ_m²/D).
   - So where the front moves at speed v, the micro-band spacing is
     v T δ_m²/δ. The spacing follows the growth rate, as Jones suggests.
2. **Linking assumption:** the fast rhythm shows only in the clear,
   impurity-poor half of each visible cycle (below the impurity's midrange),
   since iris occurs only in pure chalcedony. Elsewhere there is no grating.
3. **Preset** `iris-mechanistic`: the procedural iris preset's cavity, seed and
   0.3 mm slice, with H1's defaults and the fast rhythm on.
4. The app shows on/off settings as checkboxes, and hides δ_m while the rhythm
   is off (a `used_when` hint, now shared in `agatesim.params`).

## Results

- `iris-mechanistic` passes both iris tests at 768 px: median micro-band
  spacing 2.47 µm (1–65 µm; 5th–95th percentiles 1.3–4.1 µm), and the
  rendered colours follow the grating equation (median error 0.06 nm). It
  passes at 384 and 256 px too.
- Without the fast rhythm it fails both tests; with δ_m at 0.06 µm the median
  spacing is 0.89 µm and it fails the spacing test.
- The spacing scales with δ_m² exactly (a test), and gratings appear only in
  the clear half of each cycle (a test).
- Every other preset is unchanged: the rhythm is off by default.

## Consequences

- **Iris can't be verified at the mechanistic tier yet.** The registry makes
  iris depend on shadow, which is still pending (ADR 0041). The iris tests
  don't use shadow's, so whether the dependency should stay is the owner's
  decision.
- What sets δ_m, and whether a fast rhythm with the visible rhythm's chemistry
  is what happens, are open: δ_m is chosen so the spacing lands where Jones
  measured it, as δ itself sets the visible bands' scale.
