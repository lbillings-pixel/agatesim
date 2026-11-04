# 78. Band material that varies along each band: pigment lenses and a translucency drift

- Status: accepted (owner, 2026-11-04: lenses plus drift; lens thickness below 1 mm,
  trying 0.5 and 0.1 mm; two lengths and two strengths for look cuts)
- Date: 2026-11-04
- Builds on: [ADR 0003](0003-model-architecture.md) (labels),
  [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule needs),
  [ADR 0076](0076-changes-for-nodule-n2.md) (smooth growth time, band-pass noise),
  [ADR 0077](0077-wall-features-clear-layer-and-channels.md) (the feature layer; its
  section 5 sketched this interface)
- Spec: Nodule's ADR 0015 sections 2 and 7, option C

## Context

Every band in the growth model is one material from end to end: phase, pigment, impurity
and translucency depend on growth time alone. Nodule's owner chose to let pigment and
translucency vary along each band, in 3D. The sources support the idea but give no size
or amount:

- "Laminated and lenticular agglomerates of very small hematite particles (<10 µm)"
  gather along the banding [@goetze2020, §4.3]. No lens sizes are given, and the particle
  size says nothing about how large a lens is.
- Band widths vary within sectors, and inclusions vary along bands [@howard2018, pp. 99,
  104].
- Bands keep "the same width, consistency and colour" across sector boundaries
  [@howard2018, p. 104].

So everything here is `effective` and off by default, and every coupling is an
**assumption**. Nothing rendered from it is evidence for how lenses form.

Nodule's earlier what-if faded bands in round image-level patches about 1 and 3 mm across
(its ADR 0015). The owner judged those obviously fake. That patch form is what this design
has to avoid.

## Decision

### 1. Two independent fields (owner's choice)

- **Pigment lenses.** Inside a lens, `impurity` is multiplied by up to `1 + lens_strength`.
  Most of each band stays unchanged: `lens_cover` (0.2) is the share of banded chalcedony
  in lenses, and it is an assumption the owner did not set directly.
- **Translucency drift.** `translucency` gains up to ±`translucency_drift`, slowly along the
  band (`translucency_drift_length_mm`, 20 mm; `translucency_drift_thickness_mm`, 0.5 mm;
  starting values of ours). No source describes translucency lenses, so it drifts rather
  than forming lenses.
- Each field has its own stream under a new spawn key, so turning on one leaves the other,
  the channels and all earlier streams as they were.
- Only banded chalcedony changes. The clear first layer (band −1), quartz and filaments
  stay as they were, and values stay within 0 to 1.

### 2. The form: sheets of independent noise, read at a point's growth time

The fields take a point and its growth depth (the growth time's position in mm, from the
silica supply). Depth runs through unevenly spaced sheets, each with its own independent
pattern of `BandNoise`. Between two sheets the field blends from one to the next, keeping
unit variance (`cos θ · a + sin θ · b`). Then:

- A lens lies flat along the bands wherever they run, round corners and through a channel's
  thinning, since a band is a surface of constant growth depth.
- Where a sheet's pattern barely exceeds the threshold, little depth lies above it. So a
  lens thins toward its ends, without any explicit lens shape.
- Spacing is irregular (±50%), so lenses don't set up a second, regular banding.

This reads growth time, not the wall distance of ADR 0077 section 5's sketch, because wall
distance doesn't follow the wobble or a channel's delay. It doesn't use `influence`: no
source ties lenses to channels.

**Thin lenses need no grid.** Owner's direction: thinner than the 1 mm first offered, trying
0.5 and 0.1 mm. Nodule's time grid has a 0.2 mm spacing, which can't hold a 0.1 mm lens. But
interpolated growth time is accurate far below that spacing (Nodule's `render/tgrid.py`:
p99 0.037 band periods). So a renderer finds the point's time from its grid and evaluates
the field there, and a lens is as sharp as the time is.

### 3. Sizes, as a cut shows them

Measured on the noise alone, on 1,800 lines through the field at cover 0.2, using lengths of
runs above the threshold:

| Setting | Asked for (owner) | 10th / 50th / 90th percentile |
|---|---|---|
| `lens_length_mm` = 4 | 2–6 mm | 1.7 / 4.0 / 7.2 mm |
| `lens_length_mm` = 10 | 5–15 mm | 4.2 / 10 / 18 mm |

A cut clips each lens at a random place, so the spread is wider than asked for. One octave
gave the narrowest spread (ratio 4.2; two octaves 4.8 to 5.6), so this uses one. Median length
is 0.383 of the noise's wavelength (`CHORD_PER_WAVELENGTH`).

Thickness through the sheets: 1.04 of the mean spacing at the median, with 10th and 90th
percentiles of 0.38 and 1.98. So `lens_thickness_mm` sets the spacing directly.

### 4. Starting values for the look cuts (owner's choice)

All adjustable. Each is `effective`, to be judged by the owner's eye before any statistics:

| | Values |
|---|---|
| Lens length (median) | 4 mm, 10 mm |
| Lens thickness | 0.5 mm, 0.1 mm (the owner expects 1 mm would be too much) |
| Subtle | `lens_strength` 0.5 (up to 1.5×), `translucency_drift` 0.1 |
| Strong | `lens_strength` 1.5 (up to 2.5×), `translucency_drift` 0.25 |

On this stone, band impurity runs 0.06 to 0.45 and translucency clusters near 0.2 and 0.75,
measured per band on 300,000 random points.

### 5. The interface for Nodule's renderer

- `Fields.impurity` and `Fields.translucency` hold what lies at each point, so every existing
  reader sees it.
- New `Fields.band_impurity` and `Fields.band_translucency` hold each step's own values, which
  stay a function of the step. They are None when nothing varies, and aren't stored with runs.
- `FeatureLayer.material_shift(points, t)` gives the pigment multiple and the translucency
  change at any point, with `t` on `Fields.t_smooth`'s scale. A renderer finds the layer again
  through `wall_features(model, setting, default_rng(seed))`.

### 6. What is left out

- **Variation tied to sectors.** One iris strip has sectors that look "perfectly dark", "faintly
  banded" or "quite bright" [@raman1953, p. 200, Fig. 1], but the lighting isn't stated and no
  cause is given. The same paper finds transmission depends strongly on the angle between rays
  and band planes (p. 201), so those sectors may be about direction rather than material. Howard
  reports no change of colour across sector boundaries. So raman1953 is context only here. This
  narrows the source list in Nodule's ADR 0015 section 7.
- **Quartz in a channel's furrow, escape tubes and fading band ends** (ADR 0077 sections 4 and 7):
  separate work.
- **2D.** A 2D run with either setting above 0 stops with a message.

### 7. Controls and measurements

In `tests/test_materials_along_bands.py`:

- With nothing on, a band has one material (negative control); with both on, it varies.
- No arrival time moves, with or without a channel, so ADR 0077's fold guarantee carries over.
- Round patches of the same length correlate across 2 mm of depth (above 0.3), and the check
  that lenses stay thin rejects them (negative control); sheets stay under 0.1.
- Strength and cover come out as set; sizes match section 3.
- A preview's points match a full run's bit for bit; `material_shift` matches the fields.
- The streams stay independent; the clear layer stays clear; no cut direction repeats the
  pattern with depth.

**Hashes, all off, against 7de45c6.** 200,000 points of a stone with Nodule's `n2-slice` model
settings, with and without a channel, and all 29 2D presets: identical.

**Cost** on that stone (this PC, CPU; 1 million query points of which 398,481 lie inside, best
of 3; tracemalloc's peak, including one prepare):

| Setting (with one channel, except the first) | Prepare (s) | Evaluate (s) | Peak (MiB) |
|---|---|---|---|
| No features | 0.50 | 1.52 | 189 |
| Channel only | 2.33 | 1.59 | 189 |
| Lenses and drift, 0.5 mm | 3.06 | 2.31 | 296 |
| Lenses and drift, 0.1 mm | 3.09 | 2.30 | 296 |

So both fields together add about 45% to evaluation and 107 MiB, and thickness doesn't change
the cost. `agatesim.estimate` isn't changed: nothing uses these by default, so turning them on
in the app runs about that much over its figure.

## Alternatives considered

- **Round patches through several bands.** Simplest, and storable on a grid, but it is the
  rejected fade's form.
- **Sliding one noise field with depth.** Cheaper, with one lookup per field instead of two. But
  each depth then holds the same pattern moved sideways, so a cut along the slide would show
  copies from band to band. Rejected on reasoning, before being built.
- **Listing each lens as an object.** Explicit control of shapes, but it needs a search tree and
  a harder path for the GPU. Thresholded noise gives lens shapes without one.
- **Storing the fields on Nodule's grid.** No GPU noise is needed, but a 0.1 mm lens wouldn't
  survive 0.2 mm cells, and a 0.1 mm grid already costs about 75 s to fill.
- **Pigment and cloudiness tied to one set of lenses.** Offered; the owner chose the two
  independent fields.

## Consequences and risks

- **Nodule's iron floor.** Nodule's materials give iron pigments no absorption below impurity
  0.28 and full absorption at or above it (its ADR 0014 4l). 57% of this stone's bands lie
  between 0.20 and 0.40, so many lenses would cross it, leaving a hard edge along a band: a
  possible fake tell. Nodule's renderer ADR must address this. *plausible*; not yet rendered.
- **Clear patches.** Clear stretches over the black bottom may read as the dark grey that failed
  for the clear layer (ADR 0077 section 8). Clear bands already reach 0.875, near that layer's
  0.9, so a thick stack that drifts clear is the likelier cause. *plausible*.
- **The fade again.** A milky band drifting clear loses contrast locally, close to what was
  rejected, though band by band here. The owner's eye decides (Nodule's ADR 0015 section 1).
- **Visibility.** A 0.1 mm lens may blur away under scattering in the renderer. Not yet tested.
- **A first look**, drawn from `Fields` with a plain stand-in and not with Nodule's renderer:
  lenses follow the bands around corners. At 0.5 mm they read as dark smudges and at 0.1 mm as
  fine streaks, which fits the owner's direction toward thinner lenses. This is one view, and
  not the look check.
- Nodule moves its pin, then writes its renderer ADR, whose GPU path must read the noise itself:
  two lookups per field at each sample. Any GPU path must match this CPU result.
