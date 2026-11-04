# 77. Wall features: a clear first layer, and channels where bands thin to nothing

- Status: accepted (owner, 2026-11-03: the plan in Nodule's ADR 0015 section 5, a
  short line for the focus, and channels in 3D only). Amended 2026-11-04 after the
  owner judged the look in Nodule (sections 7 and 8).
- Date: 2026-11-03
- Builds on: [ADR 0003](0003-model-architecture.md) (labels),
  [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule needs),
  [ADR 0076](0076-changes-for-nodule-n2.md) (fold check, smooth growth time)
- Spec: Nodule's ADR 0015 section 5, option B; reading notes in Nodule's
  `notes/n2-reading/step5-band-defects.md`

## Context

Nodule's stone is too orderly. In the growth model every band is a contour of one
smooth function, wall distance plus a wobble (`volume/growth.py`), so bands keep
their thickness all the way round and never end. Nodule's owner chose to add the
local features the sources describe, not random breaks:

- "These defects are absent in agates" [@cartwright2026, §5.1.1], and away from
  channels the wall layers grow "in relatively uniform thickness"
  [@walger2009, p. 128].
- At an infiltration channel the layers are "smoothly thinning out towards a point
  with a common tangent" [@walger2009, p. 116]. Each such point is one "on a
  vanishing line" (p. 118), and the channels "have the form of furrows, follow the
  course of a capillary fissure" (p. 122). Thinning-out bands lie inside "the
  non-thinning-out very first chalcedony layer" (p. 116), which is free of pigment
  (p. 117). The thinning series wraps round the ends of the fissure, and grows
  thicker away from them until the furrow fades out (p. 120).
- Channel depth is a few mm to 2–2.5 cm (p. 125). They are "often one, rarely more"
  in a fist-sized amygdule (p. 128), and random sections often miss them (p. 127).
- A "1–2 mm layer of clear unbanded quartz" lies under the pits [@howard2018, p. 99].

No source gives a thinning rate or a formula. Lateral size comes from rough
measurements on printed figures (0.5–2 cm, *speculative*; Nodule's notes, section D).

## Decision

Everything here is `effective` (ADR 0003), off by default, and describes a form.
Nothing rendered from it is evidence for how channels form. The couplings below are
**assumptions** chosen to match the sources' descriptions.

### 1. One world-fixed feature layer

`agatesim/volume/features.py` holds `FeatureLayer`, built by `wall_features(params,
setting, rng)`.

- **Stream.** `feature_stream(rng)` derives a seed sequence from the run's own, under a
  fixed spawn key. It does not touch `rng` or its count of spawned streams, so every
  existing stream is what it was. Each channel spawns its own child, so adding a
  channel leaves the others in place.
- **Resolution.** A channel is placed from the reference lattice, which depends only on
  the cavity, and then evaluated analytically at any point. A preview and a full run
  see the same channel.
- **Finding them again.** `wall_features(model, setting, default_rng(seed))` returns the
  same channels, so Nodule can aim a cut through a line.

### 2. The clear first layer (`clear_layer_mm`)

- The opening lining steps that fit in the thickness (`clear_layer_steps`) deposit one
  material: chalcedony, band −1 (not in any band), no impurity, default pigment, no
  micro-bands, translucency 0.9 (as this model's quartz).
- Growth time doesn't change, and all band draws stay as they were. The stone differs
  only inside the layer, which makes side-by-side look checks fair.
- It works in 2D and 3D, since both use `growth_fields`. In a history that opens with
  another stage (spherulites, say) there is no layer: it belongs to opening lining.
- What fills a growth step still doesn't depend on place, so the layer also lines
  filaments for the same thickness. Whether that halo looks right is for the owner's eye.

### 3. Wall channels (`channel_count`, `channel_length_mm`, `channel_lateral_mm`,
`channel_depth_mm`)

**Owner's choices.** The focus is a *short line*, as the source says. Any cut across it
shows a fan converging on one focus. Channels work in *3D only*: a 2D run with
`channel_count > 0` stops with a message.

**Placement.** The line is walked along the surface at the clear layer's inner face (or
0.05 mm from the wall if there is no layer), in four straight pieces, keeping clear of
kinks in the wall distance.

**The form.** A channel delays the front. With `z` the wall front's depth beyond the
surface, `s` the distance along the wall from the line as a share of `L` (lateral),
`H` the depth, and `Z = 3H`:

    delay = H · (1 − s²)² · fade(z / Z) · z / (z + H s²)

where `fade` falls smoothly from 1 to 0 with steepest slope 1.5. Then:

- **Thinning.** Near the surface a band's thickness is `s² / (s² + (1 − s²)²)` of
  normal: zero at the line and normal at `s = 1`.
- **Common tangent.** Bands of the stack (the first `H` mm of growth) lie on nested
  parabolas that touch the surface at the line, which matches "a common tangent" and
  the "very low angle" of the first layers (p. 128). The source doesn't say that the
  shared tangent is the wall's: that is our reading.
- **Over the line.** Bands after the stack pass over the line and return to normal by
  `Z`, as the source's "transient into the common agate banding" (p. 122).
- **Ends.** Distance to a line segment rounds the ends, so the thinning wraps round them.
- **No folds.** The delay's fall inward is at most `1.5 H / Z = 1/2` per mm, so arrival
  depth always rises with `z`. Above the line, bands can be up to twice their normal
  thickness as a result (an assumption, seen in the look cuts).
- **Overlaps.** The largest delay wins, which keeps that guarantee.
- **Only the wall.** The delay reads the wall front's own depth, so a filament deep in
  the stone isn't delayed as if it lay beside the wall. Reading the nearest surface
  instead gave small folds near filaments on 2 seeds of 10.
- **Only lining.** Other stages keep their own geometry. Where lining ends before the
  delayed front arrives, the next stage fills in; if none, the furrow stays open.

**Starting values.** Line 10 mm, lateral 8 mm, depth 5 mm: roughly the scale of Walger's
5 cm specimen (Fig. 1; onion ~4.5 mm wide, thinning over ≥ 4 mm each side). Limits:
lateral 5–20 mm, depth ≤ 25 mm, from the sources above. Nodule's stone uses one channel
and no clear layer (section 8).

### 4. What is left out

- **Quartz in the furrow.** "The central part of the infiltration channel was finally
  filled with clear quartz" (p. 117). Here the furrow is filled by whichever bands
  arrive, since material depends on time alone. Quartz there needs position-dependent
  materials: option C.
- **The fissure** through the first layer (p. 116), escape tubes [@howard2018, p. 99], and
  thinning at indentations (deferred by Nodule's ADR 0015 until it models exteriors).
- **Lines that climb inward** past a fissure's end (p. 118–119): our line stays on the
  surface.
- **Influence through the wall.** A point in another lobe, close to a line through the
  host rock, could feel it. This is from the formula and has not been tested.

### 5. The interface option C will use (written, not built beyond `influence`)

`FeatureLayer.influence(points, d_wall)` gives, per channel, a world-fixed share from 0
to 1, which is 1 on the line and 0 outside a compact zone. It reads place alone, not
bands. Option C (materials varying along a band) would add:

- `FeatureLayer.material_shift(points, d_wall) -> (n, k)`: per-point modifiers made
  from `influence` plus new along-band fields, each from its own feature stream.
- New `Fields` that a renderer reads with the growth step, so what fills a step depends
  on place too. Nodule's `BandRecord` refuses this today (its ADR 0007 section 3), which
  is why C needs an ADR there as well.

C changes no arrival times, so B's fold guarantee carries over.

### 6. Controls and measurements

In `tests/test_features.py`:

- With no features the stone is unchanged. Before/after hashes also match (below).
- A cut across a line: bands thin to under 0.1 mm of 2.5 mm at 0.2 mm from the line, and
  thicken steadily to normal at 12 mm. A cut past the line's end, and a stone with no
  channel (negative control), give normal thickness all the way along.
- Fold check: zero. A channel with too fast a fade (negative control) does fold.
- A preview's points match a full run's bit for bit.
- A growth step stays one material; the clear layer isn't thinned at a channel; the
  stone stays fully filled, as Nodule's renderer needs.

Measured on Nodule's `n2-slice` stone (this PC, CPU), with a 1.5 mm layer and one channel:

- **Evaluation:** 1.50 → 1.53 s per million points (+2%); peak Python-tracked memory
  (tracemalloc, which includes NumPy arrays) 140 → 144 MiB. Placing one line took 1.85 s
  when measured on a freshly prepared stone. `agatesim.estimate` is left unchanged, as
  these are small against its margins.
- **Fold check near the line, seeds 1–24, 7,892–14,710 pairs each:** zero folds, measured
  from the nearest growth surface (wall or filament).
- **Hashes, features off:** 200,000 points of the `n2-slice` stone and all 2D presets
  identical to before the change.

### 7. Bands that end short of the line (`channel_opening_mm`, off by default)

**Owner's choice.** Channels close neatly on the line: the default is 0, and the setting
stays for later. Walger describes closure (section 3). Whether bands should ever end
open or fade out rests on the owner's eye plus the "thinning and narrowing of the bands
around the indentations and the escape tubes" [@howard2018]. Escape tubes are a separate
feature for later (section 4), and fading needs option C's position-dependent materials.

**The form.** With `g` the opening at the nearest place on the line and `o = H (g / L)²`,
on the surface and inward:

    delay = H · (1 − s²)² · fade(z / Z) · (z + o) / (z + o + H s²)

- `o = 0` gives section 3's formula exactly. Depths short of the surface stay undelayed,
  so a clear layer keeps its thickness.
- Above zero, the delay on the surface is above zero too, so each band ends on it: the
  stack's middle band at `g` from the line, outer bands farther off and inner ones nearer.
- `g` is drawn for each side at each point of the line, from 0 to `channel_opening_mm`,
  and blends smoothly along the line and between sides (`SIDE_BLEND_MM` = 0.5).
- The last factor only rises with `z`, so the fall inward is still at most 1/2 per mm,
  and section 3's guarantee against folds holds.

**The look (owner, in Nodule).** 1 mm is invisible and 3 mm is subtle, because bands meet
the wall nearly tangent: moving where they end changes little of what a cut shows.

**Placement.** Anchor points no longer depend on the clear layer's thickness, so a thicker
layer moves a line only inward, onto the layer's face. With no layer, lines are exactly
where they were. Stones with both a channel and a clear layer differ from 77f34ad.

**Checks.** In `tests/test_features.py`: the outer bands end short of the line, with a
closed channel as the negative control; the opening varies along the line and between
sides; 0 gives section 3's formula; the opening doesn't move the line; and the fold and
clear-layer tests run at both 0 and 1 mm. Fold check near the line with 1 mm, seeds 1–24:
zero folds.

**Measured** on Nodule's `n2-slice` stone (this PC, CPU; 1 million points, best of 3):

| Setting | Time (s) | Peak Python-tracked memory (MiB) |
|---|---|---|
| No features | 1.25 | 140.6 |
| One channel, 77f34ad | 1.32 | 143.7 |
| One channel, opening 0 | 1.31 | 143.7 |
| One channel, opening 1 mm | 1.32 | 143.7 |

So the opening's cost is too small to measure, on or off. A channel costs about 5% and
3 MiB against no features.

**Hashes against 77f34ad.** 200,000 points of that stone are identical with no features
and with one channel and no layer, so the look the owner approved doesn't change. All 29
2D presets are identical too. A stone with a channel and a 1.5 mm layer differs, as above.

### 8. The clear layer stays off on Nodule's stone (owner, 2026-11-04)

Rendered in Nodule, the clear layer shows as a dark grey ring, which the owner finds an
obvious fake tell. It stays off on Nodule's stone until that is solved. The setting
remains here, and sections 2 and 6 still describe what it does. This is a verdict on how
it looks, not on the sources' description of an unbanded first layer.

## Alternatives considered

- **A single-point focus.** Simpler, but the source is explicit that it's a line, and a
  dimple would look unlike a furrow. Owner chose the line.
- **Channels in 2D too.** A second placement path and more tests, for a mode nothing
  here needs. Owner chose 3D only.
- **Editing the wall distance before the wobble.** Simpler code, but the wobble's cap
  assumes unit slope, so with a delay under it bands could fold.
- **Fans as straight rays.** No common tangent, against the source.
- **Random pinch-outs anywhere.** Against the sources (Context).
- **Snapping the clear layer to a band edge.** Simple, but thickness would be off by up
  to half a band (~0.2 mm on Nodule's stone); per-step is exact to one step (0.075 mm).

## Consequences

- Nodule moves its pin here, turns the channel on in `n2-slice` with the clear layer
  off (section 8), and records the owner's verdict in its ADR 0015.
- Near a line, bands get thinner than Nodule's 0.2 mm time grid, so they blur together
  there. Walger's Fig. 17b also shows them unresolved in a grey wedge near the focus,
  but that match is not evidence for this form.
- `band == −1` inside chalcedony now occurs in 3D growth stones. Statistics that count
  `band >= 0` as banded already treat the layer as unbanded, as intended.
- The settings show in the app for 2D runs too. Channels there stop with the message.
