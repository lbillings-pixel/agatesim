# 38. Botryoidal agate at the mechanistic tier

- Status: accepted
- Date: 2026-10-17
- Builds on: [ADR 0008](0008-drawn-cavities-nucleation-and-crystal-growth.md), [ADR 0013](0013-mechanistic-front-feedback.md), [ADR 0035](0035-what-the-mechanistic-tier-requires.md)

## Context

The procedural botryoidal form grows lobes from nucleation sites on the wall
(a weighted Voronoi construction), but its bands are imposed. ADR 0035 proposed
applying H1's band history along each point's distance of growth from its
spherulite instead of along the wall distance.

## Literature

- Agate growth often starts as spherulitic chalcedony at the wall, continuing
  into fibrous chalcedony ([@goetze2020] §4.1.2, §5.4); fibres radiate from
  separate nucleation points at the wall before banding parallel to it sets in
  ([@cartwright2026] §5.1.1).
- Under a large driving force, phase-field models approach a universal
  spherulitic form with radial needle-like structure, whatever the early
  morphology ([@granasy2005], abstract): growth radiating from a site at one
  rate is the limit used here.

## Decision

1. **`growth_form = "spherulitic"`** for H1. Sites are placed on the wall as
   in the procedural model (blue noise, `spherulite_spacing_mm`), and each
   grows at its own rate (`spherulite_rate_variability`); both `effective`.
   The front history of H1 is unchanged; each point takes the front's state at
   its own growth distance from the spherulite that reaches it first. In the
   boundary-layer approximation the front is the same everywhere, so this is
   H1 with a different front shape, and bands are surfaces of equal growth time
   about the lobes. The cavity's filled share, which drives a closed cavity's
   reservoir, is computed from the same distances.
2. **`supply_ends_at`** (`effective`, default 1 = never): the share of the
   cavity filled when the fluid supply ends and growth stops. It is the timing
   of a change in conditions, like the staged model's rim share, so ADR 0035
   allows it (rule 2). Botryoidal surfaces line open cavities, so growth must
   stop before the cavity fills.
3. **Why not a closed cavity.** A closed cavity also leaves the centre open,
   but its falling silica ends H1's oscillation after a few bands (3–4 on this
   cavity, against 42 when open; see ADR 0037's amendment). The lobes then hold
   almost no bands, which wouldn't be botryoidal agate.
4. **Verification preset** `botryoidal-mechanistic`: the procedural preset's
   cavity, seed, site spacing (10 mm) and rate spread (0.3), supply ending at
   half the cavity.
5. Not available in 3D yet (rejected with a message).

## Results

- Passes at 768 px: lobate-front 0.88 (≥ 0.6), 13 lobes (≥ 5),
  bands-follow-lobes 0.97 (≥ 0.7). At 384 and 256 px: the same 13 lobes,
  0.91 and 0.93, 0.97 both.
- Robust at 512 px: supply ending at 0.3 or 0.5 of the cavity with 6 or 10 mm
  spacing all pass (11–23 lobes).
- On the same cavity with lining growth, lobe-count and bands-follow-lobes
  fail, as they must (a test).
- Existing H1 presets are bit-identical (the new parameters default to the
  old behaviour).

## Consequences

- Mechanistic tier: 7 of 12 forms. Eye agate, which depends on botryoidal,
  can now be tried: a spherulitic stage followed by lining growth.
- The rate spread between spherulites is an effective parameter with no
  measurement behind it; without it, equal lobes would meet in straight seams.
