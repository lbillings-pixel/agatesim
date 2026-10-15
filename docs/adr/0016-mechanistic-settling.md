# 16. Mechanistic settling (H4): horizontal layers from hindered settling

- Status: accepted
- Date: 2026-10-15
- Builds on: [ADR 0013](0013-mechanistic-front-feedback.md)

## Context

H4 attributes horizontal (Uruguay, waterline) bands to particles settling under
gravity. One review gives the particles as flocculated silica ([@goetze2020]
§4.1.2). One study finds the bands are quartz grains and spherulites deposited
after the wall-lining bands ([@lu1994], abstract). The procedural waterline
model places flat layers by height directly. A mechanistic model should make
them flat for a physical reason.

## Decision

1. **Model** `mechanistic-settling` (`agatesim.models.settling`). It uses Kynch's
   kinematic theory of batch settling [@kynch1952], in the cavity's own width
   profile along gravity:

       ∂(W φ)/∂t + ∂(W f(φ))/∂z = ∂/∂z (W D ∂φ/∂z),   f = −w₀ φ (1 − φ/φ_max)ⁿ

   - φ is the particle volume fraction and z the height along −gravity.
   - W(z) is the exact chord width of the cavity polygon, so the column does not
     depend on any pixel grid.
   - The flux is the exact (Godunov) flux for this concave law. A dilute
     suspension over a denser one passes the smaller flux, so a bed can only grow
     upward. (An Engquist–Osher flux, tried first, drew particles back out of the
     bed.)
2. **The bed.** A cell becomes bed at the gel point (`gel_point` × φ_max), where
   settled particles form a network. Kynch's flux only reaches zero at φ_max, so
   a packing threshold near φ_max would never be reached.
3. **Pulses and layers.**
   - Pulses of particles arrive at regular intervals, each spread through the
     fluid above the bed.
   - A layer ends where deposition pauses for more than half the cavity's
     settling time.
   - Each layer's iron and clarity belong to its pulse: a property of the
     supply, drawn from the seed.
4. **Horizontality** follows from the suspension being uniform across the
   cavity, which is Kynch's assumption. Convection and wall effects (the Boycott
   effect) are left out, as H1 leaves out variation along its front.

## Results

- `waterline-mechanistic` (40 mm round cavity) passes every waterline criterion:
  - gravity-normal 1.000;
  - planar 2 × 10⁻¹⁵;
  - floor-confined 0.15;
  - geopetal 0.001;
  - 12 layers.

  The registry marks waterline verified at the mechanistic tier. A 256 px
  preview fills the same share of the cavity to within 0.002. Runtime is about
  5 s.
- **Prediction 1, width.** A pulse's volume spreads over the cavity's width, so
  layers thin where the cavity widens (tested in a V-shaped column). In a round
  cavity the lowest layers are the thickest. This can be checked on specimens:
  for example, does layer thickness on a slab's floor follow the cavity's width?
- **Prediction 2, merging.** Pulses arriving faster than the particles clear
  (at about the free settling time, or more often) don't leave separate layers.
  They build one continuous deposit (tested). Distinct Uruguay layers therefore
  imply pauses between supply events at least comparable to the settling time.

## Consequences

- Waterline is verified mechanistically on the uniform-suspension assumption,
  which is stated, not hidden.
- The combined form (fortification then waterline) could chain H1 or H2 with
  H4. That needs the models to run in sequence on one cavity, which is still to
  build.
