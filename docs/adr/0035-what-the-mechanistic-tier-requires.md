# 35. What the mechanistic tier requires, form by form

- Status: accepted (owner approved, 2026-10-17)
- Date: 2026-10-17
- Refines: [ADR 0005](0005-verification-tiers-and-parameter-natures.md)
- Follows: [ADR 0034](0034-closing-the-corner-question.md)

## Context

Four of the twelve forms are verified at the mechanistic tier (fortification
and seam by H1, waterline by H4, the combined form by H1 then H4). The other
eight have had no mechanistic work. ADR 0005 says what the tier is for, but
not what a mechanistic verification must show. The code checks only that the
preset is named `<id>-mechanistic`, uses a `mechanistic-*` model, and passes.
That would let a model pass on an imposed feature. This ADR sets the rule
first, then audits the eight forms against it.

## Decision: the rule

A form is verified at the mechanistic tier when its `<id>-mechanistic` preset
passes every criterion of the form in CI (as now), and in addition:

1. **Nothing the criteria judge is imposed.** The preset sets no parameter of
   nature `imposed`. Every feature a criterion measures emerges from a
   modelled process (growth, diffusion, aggregation, settling, light
   scattering), with `physical` or `effective` parameters only.
2. **Conditions may be scheduled; forms may not.** A change in conditions
   (a stage order, a fall in silica, the start of a dendrite stage) may be
   imposed, as the staged model already does (ADR 0020): agates record such
   changes and the model doesn't explain them. A schedule that sets a judged
   feature directly (a band's duration or contrast) is not allowed.
3. **Each process has a source.** The process is described in the literature
   for agate or for the mineral concerned, recorded in the catalogue at an
   honest `checked` level. A stand-in invented to produce the form (for
   example, a preference for upward sticking) doesn't count.
4. **Assumptions linking a process to what the criteria see are stated** in
   the form's ADR (for example, which bands are milky), and are not tuned
   form by form to pass.
5. **Dependencies verified first**, at the mechanistic tier (ADR 0005, as now).

The verified four meet this rule: H1 and H4 set no imposed parameters, and the
staged model imposes only the order of stages and the rim's share.

## The audit

Probes run for this ADR are marked; everything else is reading the code.

| Form | Depends on (mechanistic) | What exists | What's missing | Cost |
|---|---|---|---|---|
| **moss** | none | Multi-particle aggregation (DLA) of diffusing particles, all parameters `effective`; dendrites as aggregation is supported ([@hou2023], full text; [@chopard1991], abstract). | The enclosing chalcedony comes from the procedural growth model with imposed bands. Moss's criteria judge only the inclusions, but rule 1 forbids imposed parameters in the preset. Needed: a dendrite stage in the staged model, enclosed by H1. | low |
| **quartz-centre geode** | fortification ✓ | *Probe:* H1 in a closed cavity (silica inventory 0.8, quartz below 0.5) passes `phase-transition` (0 of 38,892 quartz pixels touch the wall): quartz follows chalcedony because the dissolved silica runs down ([@goetze2020] §6). Geometric selection of crystals exists in the growth model ([@vanderdrift1967], citation). | H1's quartz has no crystals, so `inward-coarsening` can't be measured. Needed: H1's quartz zone filled by the existing crystal growth (crystals nucleating where H1 switches to quartz). | low–medium |
| **botryoidal** | fortification ✓ | Spherulitic growth from nucleation sites (a weighted Voronoi construction), site spacing `effective`. | Its bands are imposed. Needed: H1's band history applied along the spherulite's growth distance instead of the wall distance (the boundary-layer form depends only on how far the front has come). Literature on spherulitic chalcedony ([@heaney1993], [@shtukenberg2012], [@granasy2005]) to read beyond abstracts. | medium |
| **eye** | botryoidal | As botryoidal, with a spherulitic stage followed by layered growth. | The same, plus a scheduled switch from spherulitic to layered growth (allowed by rule 2). | low after botryoidal |
| **tube** | eye | Filaments as solid seeds lined by later growth. | H1 lining around seeds (the wall distance already includes seed surfaces). | low after eye |
| **shadow** | fortification ✓ | *Probe:* H1 bands through the existing shadow renderer: `alternating-translucency` 0.42–0.44 (needs 0.6) at catalysis 17–80; `angle-dependent-shadow` 0.23–0.34 (needs 0.3). | H1's milky/clear contrast is an assumption (impurity-rich bands milky, linear in log impurity) and falls short. Raising it to pass would break rule 4. Needed: a sourced link between what H1 varies and milkiness (fibre type, porosity or water content), and the renderer's coefficients sourced (ADR 0010 calls its shadow model a hypothesis). | medium–high |
| **iris** | fortification ✓, shadow | Grating renderer; micro-band spacing is `imposed`. | A process that makes regular micro-bands about 2 µm apart. Self-organised oscillatory zoning at micrometre scale is H1's own claim ([@wang1990], citation; [@cartwright2026] §5.1.1), so H1 at a micrometre scale nested inside the macro bands is the candidate. Needs reading first. | high |
| **plume** | moss | The upward preference is a stand-in (ADR 0009), not a mechanism. | A model of the silica garden or of buoyant flow that drives upward growth ([@goetze2020] §5.5; [@haudin2014], abstract). A new model and a literature pass. | high |

## Recommended order

1. **moss** — smallest step; adds a dendrite stage to the staged model, which
   plume will reuse.
2. **quartz-centre geode** — H1 already gives the transition.
3. **botryoidal → eye → tube** — one generalisation of H1 (bands along any
   growth distance) opens three forms, after a literature pass on spherulitic
   chalcedony.
4. **shadow**, then **iris**, then **plume** — each needs new sourced physics
   and is left until the owner chooses to take it on.

If the first five land, the mechanistic tier goes from 4 to 9 of 12.

## Consequences

- `tests/test_criteria.py` will also check rule 1: a mechanistic verification
  preset sets no `imposed` parameter.
- Each form gets a short ADR when it is verified, stating its process, sources
  and linking assumptions (rules 3 and 4).
- Shadow, iris and plume stay pending at the mechanistic tier, with their gaps
  written down here.
