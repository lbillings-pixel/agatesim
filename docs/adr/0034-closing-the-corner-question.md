# 34. Closing the corner question

- Status: accepted (owner decision, 2026-10-16)
- Date: 2026-10-16
- Concludes: [ADR 0015](0015-mechanistic-liesegang.md), [ADR 0017](0017-h1-without-the-boundary-layer.md), [ADR 0026](0026-corner-benchmark-from-high-resolution-photos.md)–[ADR 0030](0030-h1-with-weak-silica-depletion.md), [ADR 0032](0032-a-front-solver-for-fast-fronts.md)

## Context

The corner question asked whether a mechanism whose supply diffuses through
the cavity can keep fortification's sharp corners with bands of equal
thickness around them. It has taken about ten ADRs and milestones M14–M17,
while the mechanistic tier stayed at 4 of 12 forms. Its answer has converged.

## What the evidence says

- **H2 (Liesegang)** rounds corners: 1.6–2.4 band spacings in 2D (ADR 0015),
  and no random cut passes fortification in 3D (ADRs 0027, 0033).
- **H1 with explicit diffusion** doesn't oscillate at all (ADR 0017). With an
  adsorbed surface state it does, but:
  - with the silica-starved sets, its front needs smoothing; the mitres are
    then sharp, but the corner lags and bands thin toward it, to 0.68–0.78 of
    their mid-face thickness (ADRs 0028, 0032);
  - with weakly depleted, switch-like sets, the corner runs ahead and the fast
    state ends the banding (ADR 0030 amendment).
- **Real agates**: corners are sharp to moderately rounded (0.03–0.63 band
  spacings, ADR 0026), and marker bands keep their thickness toward corners
  (median 1.02, 95% interval 0.92–1.11, three photos; ADR 0029).
- **Only H1's boundary-layer form** reproduces fortification. Its assumption
  is that every part of the wall sees the same supply.

## Decision

1. **Working conclusion.** Within the models tested, fortification's corners
   point to wall growth that the whole wall sees equally: a well-mixed cavity,
   or growth limited by the surface reaction rather than by diffusion through
   the fluid. Diffusion-limited mechanisms tested here don't produce it. This
   is a conclusion about these models, not proof of how agate forms.
2. **H1's verifications** for fortification and seam stay as they are, at the
   mechanistic tier in the boundary-layer approximation (ADR 0013), now read
   as the well-mixed case.
3. **No further corner simulations** unless the owner asks.
   `scripts/h1_front_2d.py` and the H1 stability scripts stay as research
   scripts, frozen.
4. **Left open, in the backlog**: weakly depleted H1 with gentle catalysis in
   a corner (ADR 0030); what could keep a cavity well mixed (the owner's
   question about pressure-driven stirring, ADR 0030); more photos with marker
   bands.

## Consequences

- Effort turns to the mechanistic tier for the eight pending forms, and to
  the web app.
- The README's findings already state the conclusion in these terms.
