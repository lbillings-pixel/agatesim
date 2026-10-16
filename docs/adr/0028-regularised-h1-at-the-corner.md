# 28. A regularised H1 at the corner: sharp mitres, lagging corners

- Status: accepted
- Date: 2026-10-16
- Builds on: [ADR 0017](0017-h1-without-the-boundary-layer.md), [ADR 0022](0022-corners-at-the-bands-own-corner.md), [ADR 0026](0026-corner-benchmark-from-high-resolution-photos.md)

## Context

H1 with explicit diffusion and an adsorbed surface state oscillates in 1D, but
its front is unstable to ripples of every short wavelength, so the 2D corner
test had no converged answer (ADR 0017, second amendment). The photo benchmark
(ADR 0026) found real corners from as sharp as the photos resolve to moderately
rounded (0.03–0.63 band spacings), never as rounded as H2 (1.6–2.4). The owner
chose to test a regularised H1: one that smooths the front along itself, and
might round corners a little, as in n01 and the polygonal agate.

## Literature

- In crystal-growth theory, a growing front is unstable to ripples unless
  something smooths it; the classic smoothing is capillarity, the Gibbs–Thomson
  shift of solubility at a curved surface ([@mullins1964]; read at citation
  level only).
- The Wang–Merino agate model includes it. Its front is morphologically
  unstable, the bumps become chalcedony fibres, and a linear analysis with
  surface tension gives a preferred fibre thickness of a few micrometres
  ([@merino1994], a two-page abstract read from the scanned pages).
- Local models where the front's speed depends on its curvature are standard
  ([@brower1984]); the solver uses the level-set method ([@osher1988]). Both at
  citation level.
- No study modelling corner rounding in agate was found.

## Decision

Two candidate smoothings were compared, each with one parameter, labelled
`effective`:

- **surface diffusion of the coverage** θ along the front (D_θ);
- **a curvature (Gibbs–Thomson) term**: the silica that drives growth is reduced
  by γκ, so U = k (s − γκ) (1 + β aⁿ/(a_cⁿ + aⁿ)) / (1 + (θ/θ_c)^m), with κ > 0
  where the front bulges into the fluid. γ is a length, in impurity screening
  lengths.

Neither changes a straight front, so the 1D oscillation is kept as it is.

1. **Exact linear analysis** (`scripts/h1_regularised_stability.py`) extends
   ADR 0017's ripple analysis with both terms.
2. **A 2D solver** (`scripts/h1_front_2d.py`, GPU). The old scratch solver was
   lost, so it was rebuilt: a level-set front, front values from a quadratic fit
   along the normal that satisfies the flux conditions, and ghost values for a
   plain 5-point Laplacian. The front state (speed and coverage) is held by the
   fluid node next to the front and copied along the normal. Per-node copies of
   θ drift apart, because the coverage law alone is bistable. It stays a
   script, as the owner agreed, not part of the package.
3. **Parameter sets.** Re-running ADR 0017's scan (20,000 sets, seed 0) gives 9
   oscillating sets, not the 7 reported then; that list wasn't kept. An
   independent 1D front-frame solver finds converged limit cycles for 4 of
   them, which are used here:

   | Set | Period | Band step (screening lengths) | γ_c | s_f |
   |---|---|---|---|---|
   | 0 | 7.09 | 0.085 | 4.90 | 0.14 |
   | 2 | 10.3 | 0.152 | 0.87 | 0.19 |
   | 5 | 10.7 | 0.383 | 0.64 | 0.24 |
   | 6 | 3.59 | 0.275 | 1.01 | 0.31 |

   s_f is the silica at the steady front, as a share of the bulk.

## Results

### Which smoothing works

- **Surface diffusion of the coverage never gives a cut-off**, in any of the 9
  sets, even at D_θ = 100. At short wavelengths a bump still grows from the
  silica field alone (a bump reaches richer fluid), which no coverage term
  touches.
- **The curvature term always does.** Above a critical γ_c of 0.64–7.9
  screening lengths, no wavelength has a stationary instability and short
  ripples decay. Below it, a band of finite wavelengths grows, so the front
  becomes cellular at a selected scale. Long-wavelength oscillatory modes still
  grow above γ_c, nearly as fast as the uniform rhythm.

### Checks of the 2D solver

- **Straight front against the 1D solver** (γ above γ_c, h = 0.05): periods
  and band steps agree within 1% for sets 0, 2 and 6 and within 5% for set 5
  (for example set 6: 3.65 and 0.279 against 3.59 and 0.275).
- **Front values** at an imposed speed: within 0.1% of the exact steady front
  at h = 0.05, converging at second order.
- **Ripples against the exact dispersion relation** (set 0): decaying ripples
  match in rate and frequency (k = 3: −1.649 + 3.23i against −1.651 + 3.25i;
  k = 2: −0.421 + 2.33i against −0.424 + 2.35i). A growing ripple matches in its
  early, linear stage (0.347 against 0.354) before it saturates.
- **Without the curvature term**, the 2D front stops growing within the first
  60 time units at both grids (ADR 0017's earlier attempt broke into patches):
  the ill-posed case.

### The corner (quarter of a square cavity, 50 screening lengths across)

Runs with γ above and below γ_c, sets 2, 5 and 6, grids h = 0.05 and 0.025.

- **The mitres are sharp to moderately rounded.** Bands from the two faces
  meet at a seam on the bisector. Measured on rendered slabs with ADR 0026's
  mitre measure (structure tensor at 3 px, 160 px per screening length), the
  turn width is 0.16–0.53 band spacings in six runs, within the photos' range
  (0.03–0.63). So the corners do round a little, by about the photos' amount.
- **But the corner lags.** The front's tip on the bisector advances at about
  74–81% of the speed a sharp corner needs. The lag behind a sharp corner grows
  steadily, to 2.2–4.2 screening lengths (6–11 band spacings, set 5) by the
  end of the runs. More curvature reduces it (set 5 at t = 300: 6.3 at
  0.3 γ_c, 3.1–4.2 at 1.5 γ_c, 2.2 at 2 γ_c). The lag isn't grid-converged: at
  t = 150 it is 1.55 at h = 0.05 and 2.33 at h = 0.025 (a run at h = 0.0125 is
  pending). The finer grid lags more, so the lag is not a coarse-grid artefact.
- **So the bands become wedges.** Along each face, the lining 13 screening
  lengths from the wall corner is 78–85% as thick as at the face's middle (24.5),
  in every set, γ and grid tested. The fortification archetype is defined by
  bands that follow the wall; whether real bands also thin toward corners is
  not yet measured, and the photos can test it (see Consequences).
- **And the rhythm drifts out of phase along the faces.** Mirrored into a full
  square slab, the bands look like fortification at a glance, wall-following
  with sharp diagonal mitres, but neighbouring bands cross at low angles in a
  plaid pattern. This is the long-wavelength oscillatory mode of the linear
  analysis.
- **The archetype criteria were not applied.** They need band labels. Here the
  band stripes cross and merge, and the seam along the bisector fills very fast
  (the tip of the lagging finger), which joins neighbouring stripes, so any
  labelling of bands is ambiguous.
- **Below γ_c** the front is cellular. Bands are wavy and cross, and a deep
  channel opens along the bisector.

### Why the corner lags

In every oscillating set found, silica at the front is depleted to 14–31% of
the bulk: growth is limited by supply through the fluid. A corner is fed from
less fluid than a face, so it grows more slowly. This is H2's reason for
rounding (ADR 0015), and the corner lag seen without regularisation in
ADR 0017. The curvature term rounds the lagging tip but can't make it keep up.

### How large γ would be

Capillarity in silica–water is a nanometre-scale effect: with an interfacial
energy of order 0.1 J/m² and silica's molar volume, the capillary length is of
order 1 nm [assumption: no sourced interfacial energy was found in the time
box]. γ_c is 0.6–8 impurity screening lengths, and the screening length must be
several band spacings, so tens of micrometres to millimetres for visible bands.
Physical capillarity is thus far below γ_c: the real front, in this model,
would be cellular at a fine scale, which is [@merino1994]'s fibre picture.
Above γ_c, the curvature term would be an effective stand-in for unmodelled
smoothing, not capillarity.

## Consequences

- **Answer to the owner's question.** A regularised H1 does round corners a
  little, by the photo measure about as much as real agates (0.16–0.53 band
  spacings). But the corner falls behind, the bands thin toward it, and they
  drift out of phase and cross. That is not the fortification pattern as the
  archetype defines it, and the photos can test the thinning directly. With
  physical capillarity the front would instead be cellular.
- **H1 status unchanged.** H1's fortification and seam verifications stand as
  boundary-layer-approximation results (ADR 0013, ADR 0017). The
  boundary-layer approximation is in effect the assumption that the corner and
  the face see the same fluid. Every explicit-diffusion version of H1 or H2
  tested so far makes corners lag or round.
- **A test on photos.** The thinning of bands toward corners is measurable on
  real agates: [ADR 0029](0029-bands-toward-corners-in-real-agates.md) finds
  marker bands in two reference photos mostly keep their thickness (median
  1.04 of mid-face a quarter of the way from a corner, against the model's
  0.68–0.78).
- **Backlog:**
  - whether a supply that is less diffusion-limited (higher s_f) can oscillate
    at all in this model, since that is what a corner needs;
  - a sourced silica–water interfacial energy;
  - the lag's convergence on finer grids.
