# 37. The quartz-centre geode at the mechanistic tier

- Status: accepted
- Date: 2026-10-17
- Builds on: [ADR 0008](0008-drawn-cavities-nucleation-and-crystal-growth.md), [ADR 0013](0013-mechanistic-front-feedback.md), [ADR 0035](0035-what-the-mechanistic-tier-requires.md)

## Context

H1 in a closed cavity already switches from chalcedony to quartz: the bands
draw down the dissolved silica, and below a threshold quartz grows instead
(ADR 0013). The audit's probe (ADR 0035) found that this passes
`phase-transition`, but H1's quartz had no crystals, so `inward-coarsening`
couldn't be measured.

## Literature

- "Macrocrystalline quartz crystallizes when the SiO2 concentration in the
  mineralizing fluid is low" ([@goetze2020] §6), and wall-lining agates have a
  macrocrystalline quartz centre (§4.1.2). H1's closed cavity models exactly
  that fall in silica.
- Geometric (evolutionary) selection: crystals growing from a surface compete,
  and those whose fastest growth points along the growth direction outgrow the
  rest ([@vanderdrift1967], citation level). It is still studied as a
  mechanism in its own right: the chance that a seed grows into a large
  crystal depends on its orientation ([@krapivsky2019], abstract).
- No study measuring crystal coarsening in agate geodes was found.

## Decision

1. **Crystals in H1's quartz zone** (2D). Where H1 grows quartz, crystals
   nucleate on the chalcedony's inner surface and grow into the space that was
   still open, by the procedural model's crystal construction: blue-noise
   sites, prism-shaped growth forms with axes scattered about the surface
   normal, and the first crystal to arrive owns each point
   (`grow_crystals` in `agatesim.models.growth`).
2. **Three new H1 parameters**, all `effective`, with the procedural model's
   defaults: `quartz_grain_mm` (0.6), `quartz_elongation` (4) and
   `quartz_axis_scatter_deg` (70). Runs without quartz are unchanged.
3. **Linking assumption.** H1's front history says when quartz reaches each
   point; the crystals say only which crystal fills it. So the quartz front
   stays parallel to the wall, and the crystals' pointed terminations don't
   shape the open centre. Since every crystal grows at the same rate, which
   crystal wins doesn't depend on how fast the front moves.
4. **Verification preset** `quartz-geode-mechanistic`: the procedural preset's
   almond vesicle (60 mm, seed 6), silica inventory 0.8 of the cavity, quartz
   below 0.6 of the initial silica. **Nothing is scheduled**: the change from
   chalcedony to quartz and the open centre both come from the silica running
   down. That goes further than the procedural preset, which schedules the drop.
5. **3D**: H1's quartz in 3D keeps no crystals for now; the 3D geode remains
   procedural.

## Results

- `quartz-geode-mechanistic` (768 px) passes: no quartz pixel touches the wall
  (0 of 23,432), crystals widen inward with Spearman 1.0 (151 crystals, mean
  width 0.59 → 0.86 mm), and all quartz follows the last chalcedony
  (τ = 0.247).
- Robust: at 512 px, silica inventories 0.6 and 0.8 and quartz thresholds 0.4
  and 0.6 all pass (Spearman 0.68–0.99). Previews at 384 and 256 px pass
  (0.90 and 0.96).
- No new criterion, so no new negative control; the geode's existing negative
  controls apply. New tests check that crystals fill exactly the quartz zone,
  thin out inward, and are absent without quartz.

## Consequences

- Mechanistic tier: 6 of 12 forms.
- **The closed cavity ends H1's banding early.** As the dissolved silica
  falls, the front leaves its oscillating range: the preset's chalcedony holds
  only 3 bands (the same cavity, open: 25), and the incorporated impurity then
  drifts smoothly, so the rest of the chalcedony looks faintly graded rather
  than banded (found while building ADR 0038). The geode's criteria don't judge
  the chalcedony's bands, but the form is described as banded chalcedony giving
  way to quartz, so this is a limit of the H1 parameter set: one whose
  oscillation survives falling silica is still to find (backlog).
