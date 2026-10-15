# 6. Specimen photo analysis: identify, measure, replicate

- Status: accepted (plan; implementation in M7 and M10)
- Date: 2026-10-15

## Context

The owner wants users to be able to provide specimen photos, and agatesim to
**identify** the archetypal forms in a photo, **analyze** them, and **replicate**
them in simulation. This is an inverse problem, harder than forward simulation.
Photos vary in lighting, polish, viewing angle and scale, and a photo shows only
the appearance of a single cut surface.

## Decision

Treat a photo as one more producer of **observed fields**, judged by the same
machinery as simulations.

```
photo ─► observed fields ─► archetype criteria ─► identification (which forms pass)
                          └► band statistics  ─► parameter fit ─► replica run ─► side-by-side
```

1. **Same criteria, same contract.** Criteria already read only `Fields` plus
   cavity geometry (ADR 0003). Photo analysis produces an estimated `Fields`, so
   the archetype ladder identifies forms in photos with no separate classifier.
   This keeps the criteria honest twice over: they must work on real agate, not
   only on our own models.
2. **Constrained input, stated plainly.** The supported input is a photo of a flat
   cut or polished slab, taken roughly perpendicular, with a scale given (a scale
   bar or an entered size). Other photos are rejected or flagged as low
   confidence.
3. **Human in the loop first.** The user confirms or traces the cavity outline,
   using the M4 drawing tool, and the gravity direction if known. Automatic
   segmentation suggests; it doesn't decide.
4. **Staged implementation:**
   - **M7: Specimen analysis I (structure).** Upload and scale. Outline. Band
     boundaries from edge detection and an orientation (structure-tensor) field.
     Estimate the band index, translucency and iron-stain fields. Run every
     implemented criterion and report each form as identified, ambiguous or not
     present, with values. Fit **procedural** parameters directly from measured
     statistics (band spacing, contrast, fill level, gravity), run a replica, and
     show it side by side with the photo.
   - **M10: Specimen analysis II (mechanisms).** Simulation-based inference over
     **mechanistic** parameters: which conditions, under which hypothesis,
     reproduce this specimen, and with what uncertainty. Optionally a learned
     classifier, trained on the reference set plus simulated data.
5. **Reference set as test data.** The openly licensed specimen photos in
   `references/images/` become regression tests for photo analysis. For example,
   a photo catalogued as waterline banding must be identified as waterline.
6. **Privacy.** Uploaded photos stay on the user's machine in the local app.
   Nothing is sent anywhere. If a hosted version ever exists, uploads will need
   their own policy.

## Why not earlier, or larger

- Identification needs the criteria for the forms in question, so analysis
  follows the structural archetypes (M3–M5). Faithful visual comparison needs
  the optical renderer (M6).
- A learned classifier first would need many labelled specimens, and a
  classifier can't explain its answer. Criteria-based identification can.

## Consequences

- New criteria must be robust on noisy, real-world fields, not just clean
  simulation output. Photo analysis will expose criteria that are too fragile.
- A shared `band statistics` module (spacing distribution, contrast, orientation
  histogram) becomes the common language between runs and photos. It starts in
  M3 for comparing runs.
- Scope stays bounded: no 3D reconstruction from photos, and no analysis of
  rough or unpolished specimens.
