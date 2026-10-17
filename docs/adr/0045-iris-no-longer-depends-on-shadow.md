# 45. Iris agate no longer depends on shadow agate

- Status: accepted (owner approved, 2026-10-17)
- Date: 2026-10-17
- Amends: the archetype ladder ([ADR 0004](0004-archetype-ladder.md)), iris's dependencies
- Follows: [ADR 0043](0043-a-fast-rhythm-for-iris-agate.md)

## Context

The registry made iris agate depend on fortification and shadow agate, so a
tier's verification of iris needed shadow verified at that tier first
(ADR 0005). The mechanistic iris of ADR 0043 passes both iris tests, but shadow
is still pending at the mechanistic tier (ADR 0041), which blocked iris.

Iris's tests (micro-band spacing, and colours that follow the grating
equation) use neither shadow's tests nor its renderer: iris is backlit
diffraction, shadow is reflected scattering. Shadow came before iris on the
ladder because both are optical forms built in M6, not because iris needs it.

## Decision

- Iris depends on fortification only. Its rung (12) is unchanged.
- With that, iris is verified at the mechanistic tier by `iris-mechanistic`
  (ADR 0043), which CI checks like every other mechanistic verification.
- Nothing else changes: iris's tests and thresholds are as in ADR 0042.

## Consequences

- Mechanistic tier: 11 of 12 forms. Shadow is the one left (ADR 0041).
- The owner chose to keep H1's assumption that its fast, impurity-rich bands
  are the milky ones (ADR 0013), rather than reverse it on the evidence of
  ADR 0041's amendment.
