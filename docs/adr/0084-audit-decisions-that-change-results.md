# 84. Audit decisions that change results

- Status: accepted (owner, 2026-11-10: "all as recommended" for audit part C)
- Date: 2026-11-10
- Builds on: [ADR 0003](0003-model-architecture.md) (parameter natures),
  [ADR 0004](0004-archetype-ladder.md) (changing a verified criterion needs an ADR),
  [ADR 0042](0042-iris-agate.md) (iris gratings), [ADR 0069](0069-calibration-without-a-ruler.md)
  (explore ranges), [ADR 0083](0083-audit-decisions-without-result-changes.md) (batch 1)
- Audit: PR #14, part C items 1, 2, 6, 7, 8, 14 and 17

## Context

ADR 0083 recorded the audit decisions that leave results unchanged. These seven
change a result, a saved file or a schema. Each is a section below.

## Decisions

### C1. A band's iris grating doesn't depend on the band count

`base.micro_band_spacing` drew the regular/irregular coin for every band and then
every band's spacing from one stream, so band 0's spacing came after `count` coin
draws. A preview and its full run can have a band or two more or fewer, so they got
different gratings, against the rule that anything random is resolution-independent.
The coin and the spacing now come from two spawned streams, as `band_sequence`
already does. Test: `test_a_bands_grating_does_not_depend_on_the_band_count`.

### C2. The H2 lattice has the spacing it is asked for

`liesegang._lattice_grid` set the cell count from the cavity and then let
`Grid.around` add a 2% margin each side, so the lattice was 4% coarser than
`lattice_mm` (0.052 for 0.05 mm). The sliver threshold (`MIN_BAND_MM2`) used the
nominal spacing, so it counted 8% more area than it said. The lattice now has
exactly `lattice_mm` (as the 3D lattice already had) until it would pass
`MAX_CELLS`, and the threshold uses the actual spacing.

The H2 pattern is sensitive to the spacing. On the 15 mm angular test cavity,
0.038-0.042 mm gives 5 to 13 bands, and at exactly 0.04 mm 3 of 12 bands don't
close. Every other spacing in that range gives closed bands. The H2 tests now ask
for 0.0416 mm, the spacing they were written on, and give the old values exactly.
`liesegang-nodule` likewise asks for 0.052 mm, its old actual spacing. At
0.049-0.051 mm its outer bands fall under 5 px apart at 768 px, and the corner
measure declines to judge, which its discriminant test needs (corner ratio 4.0 at
0.052, as before). `liesegang-seam` keeps 0.02 mm and still passes seam (mirror
symmetry 0.978 to 0.974).

### C6. One rank function, with ties

The quartz-geode criterion `inward-coarsening` (registry: a Spearman
correlation) ranked tied widths in order of appearance. It now uses the same
`criteria.common.spearman` as the cut-shape analysis, in which ties share their
mean rank. A quartz layer whose curves all show the same width now has no value
(a message says why) instead of NaN. Value of this verified criterion: unchanged
for both shipped presets (0.988; no tied widths), so no preset's status changes.
Test: `test_spearman` checks a tie.

### C7. Rendering looks the same at any resolution

`render._sub_banding` drew three properties for every band from one stream. They
now come from three spawned streams, as in C1. `render._host_rock` drew its noise
per pixel, so a preview's host rock had a different pattern from its full run.
The rock is now built in world coordinates: the mottle on `smooth_noise`'s lattice
(1.5 mm, as before), the grain as one hashed value per 0.05 mm square (splitmix64,
as the dendrite draws of ADR 0057), and the volcanic specks at random positions in
millimetres, 0.1 per mm² (the old rate at the default 768 px). Appearance only;
criteria never read the render. Test:
`test_host_rock_grain_is_tied_to_the_world_not_the_pixels`.

### C8. Saved 3D runs keep every field

`write_volume_run` left out `grain` and `micro_spacing_um`. It now saves both. Cost
measured on four presets at their default resolution: fortification-3d 2.6 MB
+5.1%, waterline-3d 1.8 MB +2.9%, stick-mechanistic-3d 1.2 MB +2.4%,
quartz-geode-3d 0.5 MB +19% (0.09 MB). Test: `test_a_saved_3d_run_keeps_every_field`.

### C14. `max_steps` is labelled; choices and switches need no nature

H2's `max_steps` now has units (steps), bounds (1,000 to 10,000,000) and the nature
`effective`. It is a numerical limit, not a property of the gel. ADR 0003's
natures apply to numbers a model reads. Choices and switches (`micro_rhythm`,
`growth_form`, `stick_fill`, `Staged.order`, `wall_mechanism`) pick a model's form,
and are not quantities that can be physical, effective or imposed. A schedule's
numbers (when and how much) take the nature of the setting it varies. Test:
`test_every_numeric_setting_has_a_nature_and_units`.

### C17. Two defaults that disagreed with their models

- Front feedback's `spherulite_spacing_mm` default moves from 10 to 16 mm, inside
  the 13-24 mm explore range ADR 0069 set from the photos. Every preset sets its
  own spacing (botryoidal 10, eye 20), so no preset changes.
- The time estimate counted a dendrite stage as on when its schedule went above 0.
  The model grows one at 0.5 or above, and not where sticks take that time. The
  estimate now asks the model (`growth_modes`). Test:
  `test_dendrites_count_as_on_only_where_the_model_grows_them`.

## Consequences

- Field hashes change for presets with iris micro-bands (C1) and for the H2
  presets (C2); see the commit message for the list. The gallery is regenerated
  (C7 changes every slab's host rock).
- The front-feedback and Liesegang schemas changed (C14, C17), and the staged
  schema in ADR 0083, so `agatesim volume shape` recomputes their cut shapes once.
- Saved 3D runs are 2-19% larger (C8); older saved runs still open.
