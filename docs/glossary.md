# Glossary

Plain-language meanings of terms used in the docs, the web app and the ADRs.

## Agate and its forms

- **Agate.** Banded chalcedony that fills a cavity in rock, layer on layer.
- **Chalcedony.** Silica (SiO₂) made of microscopic quartz fibres. Its bands
  differ in colour, translucency and impurity content.
- **Cavity, nodule, vesicle, seam.** The space an agate fills. A vesicle is a gas
  bubble in lava, a nodule a pocket in sedimentary rock, a seam a crack.
- **Archetype.** One classic agate form (fortification, waterline, eye and so
  on), defined by measurable criteria. The [archetype ladder](archetypes.md)
  lists them.
- **Fortification.** Bands that follow the cavity wall inward and keep its
  corners as sharp angular turns, like the walls of a star fort.
- **Waterline.** Flat, horizontal layers that settled on the cavity floor.
- **Mitre.** The line where bands from two faces of a corner meet, along the
  corner's bisector. In many agates it shows as a visible seam.
- **Marker band.** A band distinctive enough, by colour for example, to follow
  around a whole agate. It records a single moment in growth.

## Measuring

- **Band spacing.** The distance from one band boundary to the next, across the
  bands.
- **Turn width.** How far a band boundary travels sideways while it turns a
  corner. Sharp corners turn within a pixel or two; rounded ones over a
  distance set by their radius. Divided by the band spacing, it is the
  corner test's number ([ADR 0022](adr/0022-corners-at-the-bands-own-corner.md)).
- **Corner lag.** When a corner's bands grow more slowly than the faces' bands,
  so each band thins toward the corner
  ([ADR 0028](adr/0028-regularised-h1-at-the-corner.md)).
- **Criterion, threshold.** A measured number and the value it must reach for a
  result to count as showing a form.
- **Negative control.** A result that lacks a form, which a criterion must
  reject. Every criterion has one, so it can't pass everything.
- **Cut, random-cut survey.** A plane through a 3D result, judged as a 2D slab;
  a survey judges many random cuts and reports how often the form shows.

## Models

- **Procedural model.** Builds a form in by design, for example by laying bands
  at set distances from the wall. It shows the simulator can represent and
  measure a form, not how nature makes it.
- **Mechanistic model.** Lets a form emerge from proposed physics. The forms it
  reproduces show what that mechanism *can* make.
- **Verified.** A committed preset passes all of a form's criteria in the
  automatic checks. Tracked separately for procedural and mechanistic models.
- **H1, front feedback.** Bands from feedback at the growth front: an impurity
  piles up ahead of the front, changes how fast it grows, and is then trapped,
  in a repeating cycle.
- **Boundary-layer approximation.** H1's simplification that the whole front
  sees the same fluid. Its bands, and its sharp corners, rest on it
  ([ADR 0017](adr/0017-h1-without-the-boundary-layer.md)).
- **Regularised H1.** H1 with explicit diffusion through the cavity and a small
  surface tension on the growth front, which stops the front breaking into
  ripples ([ADR 0028](adr/0028-regularised-h1-at-the-corner.md)).
- **H2, Liesegang precipitation.** Rings of precipitate where diffusing
  chemicals meet, like the bands in some rocks and gels.
- **H4, hindered settling.** Particles settling in pulses and packing up from
  the floor: the waterline mechanism.
- **Parameter natures.** Every model setting is labelled *physical* (a real
  quantity with units), *effective* (a stand-in for physics not modelled in
  detail) or *imposed* (a condition set from outside, such as a supply
  schedule).
- **Screening length.** The models' natural unit of length: how far the
  impurity spreads into the fluid ahead of the front before it relaxes back.
  Its real size is unknown, so results in this unit compare shapes, not sizes.
- **Diffusion-limited growth.** Growth whose speed is set by how fast silica
  reaches the front through the fluid. Corners are fed from less fluid than
  faces, so they fall behind.

## Code and records

- **Preset.** A saved run configuration that reproduces a result exactly.
- **ADR.** Architecture (or decision) record: a short note of what was decided
  and why, in [docs/adr](adr/).
- **Checked level.** How far a cited source was actually read (citation,
  abstract, sections or full text), recorded in the
  [reference catalogue](../references/catalogue.toml). Claims never go beyond it.
