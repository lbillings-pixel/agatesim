# 79. Plumes traced one by one: tilt, colour along and between plumes, clear halos

- Status: accepted (owner, 2026-11-09: one-time approval of these changes from Nodule,
  and "change the agatesim growth code to allow more color variation in a single stone")
- Date: 2026-11-09
- Builds on: [ADR 0025](0025-inclusions-in-3d.md) (3D aggregation),
  [ADR 0057](0057-a-reproducible-gpu-dendrite-engine.md) and [ADR 0061](0061-a-compiled-cpu-dendrite-engine.md) (the
  three aggregation loops give one result), [ADR 0072](0072-reframing-a-coupled-follow-on-project.md)
  (changes Nodule needs), [ADR 0078](0078-band-material-varying-along-bands.md) (steps'
  own values kept beside place-dependent ones)
- Spec: Nodule's ADR 0018 section 13

## Context

A dendrite stage gave one tint to every branch in the stone, could only favour growth
against gravity, and had no halo. Nodule's reading of Kile [@kile2002] (magazine with
editorial review, so *plausible* at most) reports that plumes are black-brown, orange-gold
or rarely red, that one plume is often "variegated orange-to-black" (pp. 259-260), and
that clear chalcedony halos commonly enclose plumes and moss (pp. 259, 263), reportedly
erasing earlier bands (p. 263). No source gives halo widths, how often plumes lean, or how
tints are spread among plumes. Nodule's owner chose plumes whose direction varies per
stone, mostly up, and asked for colour that varies within one stone.

## Decision

1. **Tracing (no change to the aggregation loops).** A particle sticks only next to a cell
   attached in an earlier sweep, because whether it touches the aggregate is decided before
   the sweep's attachments (`_dla`). So after aggregation every new cell has a parent among
   its six neighbours from earlier sweeps: the one fewest branch steps from its seed (ties:
   the first lattice offset). `trace_plumes` gives each cell its seed's plume number and
   `along`, its branch steps over the plume's largest (0 at the seed, 1 at the farthest
   tip). The GPU, compiled and NumPy loops are untouched, so ADR 0057/0061 parity holds.
2. **Settings (3D, all `effective`, all off by default):**
   - `dendrite_tint_change`: added to the base tint in proportion to `along`.
   - `dendrite_tint_spread`: each plume's base and tip tints move by up to this much
     either way, independently, drawn per plume.
   - `dendrite_tilt_deg`, `dendrite_azimuth_deg`: the direction the existing upward bias
     favours, and the side the start-height share is measured from. The aggregation
     biases one lattice axis, so the direction **snaps to one of six** (up, down, four
     sideways); tilts in between would need a change to all three loops.
   - `dendrite_halo_mm`, `dendrite_halo_share`: chalcedony within the width of a plume
     that has a halo (drawn per plume) is clear (translucency 0.9) with its impurity
     erased, fading out over the outer 30 % of the width. Before the halo, impurity and
     translucency are kept in `band_impurity`/`band_translucency` (ADR 0078), since a
     halo depends on place, not on the step.
3. **Couplings (assumptions):** tint changes linearly with branch steps; halo width is the
   same for every plume in a stone; a halo erases band colour completely. Kile supports a
   halo erasing bands and a single plume changing colour, not these forms.
4. **Streams:** each dendrite stage's per-plume draws use a child spawned from the stage's
   stream after the aggregate's own, so existing aggregates and fields are unchanged.

## Consequences

- Default results are byte-identical: cuts of plume-3d and moss-3d at 256 px hash the same
  before and after (measured 2026-11-09). Tracing adds about 0.1 s at 4 M cells; halos
  about 0.5 s per 1.7 M points.
- Tests (tests/test_volume_dendrites.py): every traced cell has a same-plume neighbour one
  step nearer its seed; tilt snaps as stated; per-plume draws; on a 3D grid, tilted plumes
  pair up along x more than along gravity's axis, tints span over 0.3, and chalcedony
  within 0.6 mm of plumes is clear. Negative controls: rising plumes must not count as
  sideways, one-tint plumes must not count as varied, plumes without halos must not count
  as cleared.
- 2D models ignore these settings.
- Procedural only: nothing here is evidence for how plumes, their colours or halos form.
