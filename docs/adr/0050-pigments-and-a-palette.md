# 50. Pigments and a palette

- Status: accepted (owner approved the scope, 2026-10-17)
- Date: 2026-10-17
- Builds on: [ADR 0003](0003-model-architecture.md), [ADR 0013](0013-mechanistic-front-feedback.md), [ADR 0016](0016-mechanistic-settling.md)

## Context

Every model coloured its bands with one stand-in, "iron", rendered from ochre
to deep red as it increases. The owner asked for a broader palette in the
procedural models, and for mechanistic colour if it wouldn't be prohibitive.

## Literature

- Colour in chalcedony comes mostly from mineral inclusions, not dissolved
  ions: hematite and goethite red-orange; Ni- or Cr-bearing clays and
  celadonite green; Mn oxides or carbonaceous matter black. Blue comes from
  light scattering, white from fine clay inclusions or scattering, and violet
  from an amethyst-like iron colour centre ([@powolny2025], read in part).
- In Moqi agate, red and yellow are mainly hematite and goethite, red holding
  more iron than yellow; green is celadonite ([@zhang2023], abstract).
- Iron pigments are rejected by crystallising silica and gather along the
  banding ([@goetze2020] §5.4): the behaviour H1 already gives its impurity.

## Decision

1. **A pigment field.** `Fields.pigment` names what `impurity` measures in
   chalcedony: iron (as before), hematite, goethite, celadonite, Mn oxide,
   violet (colour centre), blue (scattering) or white. It is optional; left
   empty, everything renders exactly as before. The renderer gives each
   pigment its own colour ramp (iron keeps its ochre-to-red ramp). Criteria
   don't read it.
2. **A palette** (`agatesim.models.palette.Palette`): a relative weight for
   each pigment, `effective`. Each band draws one pigment, in proportion,
   from its own random stream, so band k's pigment doesn't depend on how many
   bands there are. With only iron weighted (the default) no pigment is
   named. Used by the procedural growth, fortification and waterline models
   (2D and 3D) and by H4's settling pulses, where it is a condition of the
   supply, drawn per pulse.
3. **H1 trace pigments** (`FrontFeedback.trace`): iron and manganese carried
   as passive trace species by the same front feedback. Each has a
   boundary-layer concentration with its own slow-growth partition
   coefficient (`effective`) and the same trapping at fast growth, and in a
   closed cavity its own amount used up, as the catalysing impurity's
   (ADR 0013). They don't feed back on growth.
   - **Linking assumptions (rendering):** each species' stain is its log
     concentration over the chalcedony's range, times its level in the fluid;
     the stronger one colours the band. Iron precipitates as goethite before
     `hematite_from` (a share of the formation time) and as hematite after: a
     scheduled change of conditions (oxidation or temperature), not modelled.
   - Off by default: H1 results are unchanged until a level is set.
4. **Not done:** H2 (Liesegang) colour, which would need another field on the
   GPU lattice; the optical renderers (shadow, iris) still read `impurity` as
   iron.

## Results

- **Cost:** H1 with iron and manganese runs in 0.9 s at 512 px, the same as
  without (four more equations in the boundary layer, solved once per run).
- **H1:** trace iron stains the fast, milky half of each cycle more than
  twice as strongly as the slow half; the bands are where they were (more
  than 99.9% of pixels keep their band); scheduled goethite then hematite
  gives yellow bands, then red.
- **Procedural:** each band takes one pigment; fortification, waterline and
  growth models all draw from the palette; settled pulses take one each.
- **Nothing else changes:** all 27 2D presets hash bit-identical, and so do
  the 18 3D presets checked (the defaults name no pigment, and the new random
  streams come after the old ones).
- Tests in `tests/test_palette.py`.

## Consequences

- Colour is now a modelled property, though none of the archetype tests
  judge it. A future test (carnelian red, say) would need its own sourced
  criterion.
- Whether hematite or goethite forms, and what sets a band's manganese, are
  conditions the user schedules, not outcomes.
