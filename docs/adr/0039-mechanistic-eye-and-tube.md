# 39. Eye and tube agate at the mechanistic tier

- Status: accepted
- Date: 2026-10-17
- Builds on: [ADR 0020](0020-staged-mechanisms.md), [ADR 0035](0035-what-the-mechanistic-tier-requires.md), [ADR 0038](0038-mechanistic-botryoidal.md)

## Context

With botryoidal verified at the mechanistic tier (ADR 0038), eye agate (which
depends on it) and then tube agate (which depends on eye) could be tried. Both
reuse H1's front history with a different front geometry.

## Literature

- Spherulitic growth from separate points on the wall, then banding parallel
  to the wall ([@cartwright2026] §5.1.1; [@goetze2020] §4.1.2): exactly eye
  agate's sequence.
- Tube and moss filaments have cores wrapped in concentric chalcedony
  ([@goetze2020] §5.5); the filament itself (its origin, possibly biological,
  [@goetze2020b]) isn't modelled, only chalcedony growing on it.

## Decision

1. **Eye: a spherulite stage in the staged model.** `order = "spherulite-wall"`
   runs H1 with `growth_form = "spherulitic"` until it has filled `rim_share` of
   the cavity, then an H1 lining stage overgrows the eyes and the bare wall
   between them. Spherulite spacing and rate spread come from `[model.wall]`.
   Imposed: the order of the two stages and when the first ends (ADR 0035,
   rule 2); the eyes' bands, and the lining's, are self-organised.
2. **Tube: H1 lining grows from every solid surface.** H1 now grows from the
   tube filaments as well as the wall (the exact solid distance, as the growth
   model already used), and only into the open space. Without tubes the
   distance is the wall distance, so every existing preset is bit-identical
   (checked on all 17 2D presets). The filaments are part of the cavity's
   geometry, like its outline.
3. **Verification presets** `eye-mechanistic` (the procedural eye preset's
   cavity, seed and 20 mm site spacing; the spherulite stage fills 10% of the
   cavity) and `tube-mechanistic` (the procedural tube preset's cavity and
   filaments, H1 defaults).

## Results

- **Eye** passes at 768 px: 7 discrete eyes (≥ 3), all 7 rooted on the wall
  (≥ 0.8), 56% of the first banding on the wall ordinary layering (≥ 0.3). At
  384 and 256 px it passes too (7 and 10 centres; 0.46 and 0.44). With the
  spherulite stage at 3%, 6% or 10% of the cavity it passes at 512 px.
- **Counter-case** (a test): spherulites nucleated 5 mm apart and filling 30%
  of the cavity make a continuous crust, and isolated-eyes fails.
- **Tube** passes at 768 px: seed-concentric 1.0 (≥ 0.8), ring centres within
  0.3% of the ring zone's radius of their seeds (≤ 0.1); at 384 and 256 px,
  1.0 / 0.9% and 0.99 / 1.1%. The bands nearest a filament are H1's first ones,
  grown from it; without the filaments the same place holds late bands grown
  in from the wall (a test).
- No new criterion, so no new negative control; the forms' existing negative
  controls apply.

## Consequences

- Mechanistic tier: 9 of 12 forms. Pending: shadow, iris and plume, which need
  new sourced physics (ADR 0035).
- Not available in 3D yet: spherulitic H1 is rejected there, and 3D H1 doesn't
  grow from filaments.
