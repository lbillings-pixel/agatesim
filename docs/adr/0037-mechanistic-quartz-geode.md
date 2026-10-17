# 37. The quartz-centre geode at the mechanistic tier

- Status: accepted (amended 2026-10-17: why a closed cavity stops the banding; the preset now closes late, [ADR 0046](0046-a-geode-that-bands-while-open.md))
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
- **The closed cavity ends H1's banding early.** The preset's chalcedony holds
  only 3 bands (the same cavity, open: 25), and the rest of it looks faintly
  graded rather than banded (found while building ADR 0038). The geode's
  criteria don't judge the chalcedony's bands, but the form is described as
  banded chalcedony giving way to quartz, so this is a limit of the model.

## Amendment (2026-10-17): why, and a search for a set that keeps banding

- **Both closed-cavity effects stop the rhythm.** Counting the front-speed
  cycles in the preset's cavity: open, 12; closed, 1. With the silica falling
  but the bulk impurity held at its start, 2; with the rejected impurity
  concentrating in the shrinking fluid but the silica held, 8. Even with
  silica to spare (inventory 3), a closed cavity gives 1 cycle: as it fills,
  the bulk drifts out of the narrow range where this set oscillates.
- **A search for a set whose rhythm survives** (scratch scans, not kept):
  476 random sets of the six feedback coefficients and the cooperativity
  around the defaults, judged in the preset's closed cavity. Counting every
  speed cycle, the best keeps 32, but after two or three full cycles their
  impurity swing fades to a tenth (0.07 against 1.4 log units), too faint to
  read as bands. Counting only cycles that swing at least 0.5 log units, the
  best keeps 5, all within a fraction of a millimetre of the wall. No set
  tried keeps visible bands through the chalcedony, so the preset is unchanged.
- **Band finding.** H1 calls a band a crossing of one level, the midpoint of
  the impurity's range over the whole run, which also misses cycles riding on
  a strong drift. Judging each cycle against its own peak and trough would
  count them, but it changes no existing preset by more than one band, and it
  doesn't make faint cycles visible, so it wasn't adopted.
- **Where this points.** In this model a well-banded rim needs its fluid
  resupplied while it bands: an open cavity, as fortification's corners also
  suggest (ADR 0034). A geode history in which the cavity is open while the
  chalcedony bands and closes before the quartz grows would fit; it would be a
  scheduled change in conditions, which ADR 0035 allows. Done in
  [ADR 0046](0046-a-geode-that-bands-while-open.md).
