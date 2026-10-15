# 18. Discriminants: telling formation mechanisms apart

- Status: accepted
- Date: 2026-10-15
- Builds on: ADRs [0013](0013-mechanistic-front-feedback.md)–[0017](0017-h1-without-the-boundary-layer.md)

## Context

M8's mechanistic models make different predictions:
- front feedback (H1) keeps corners and closed rings;
- Liesegang precipitation (H2) rounds corners, breaks rings, and widens its
  bands inward;
- hindered settling (H4) thins its layers where the cavity widens.

M10 starts by turning these predictions into measurements. Like the criteria,
each reads only Fields and geometry, so it applies to simulations and photos
alike (`agatesim.discriminants`). Each is checked on simulations of known
mechanism, then through the photo pipeline on synthetic photos.

Literature:
- Band profiles of an agate are self-affine, with Hurst exponents 0.36 ± 0.05
  and 0.49 ± 0.05 [@holten1998] (abstract). That agrees with the 0.25–0.47 we
  measured on the owner's photos (ADR 0014).
- The Liesegang laws are a geometric spacing series and widths growing with
  position ([@cartwright2026] §4.1.5).
- No published comparison of band sequences between neighbouring nodules was
  found.

## Decision: three discriminants

| Discriminant | H1 | H2 | H4 | procedural |
|---|---|---|---|---|
| **corner ratio**: turn width over band spacing, at corners of the outline simplified at 1% of the cavity's size | 0.45 | 4.0 | – | 0.37 |
| **ring closure**: share of bands that are closed rings | 0.94 | 0.16 | – | 0.97 |
| **floor-width slope**: log layer thickness against log cavity width, one point per horizontal band | – | – | −0.11 to −1.1 over 6 seeds (−0.55 at constant dose) | −0.19 to +0.19 |

How each is measured:
- **Band thickness** is 2 × area ÷ boundary length, one value per band. This
  replaced a first version that sampled rays: slivers and spot boundaries made
  its fits flip sign.
- **Horizontal bands** are those whose boundary normals mostly lie within about
  11° of gravity.

Why H4's floor slope isn't −1 at constant dose:
- width × thickness per layer stays constant within ±5%, as mass balance
  predicts;
- but the lowest layer is excluded, because it lies curved on the floor, and
  that narrows the width range of the fit.

**Dropped: the Liesegang spacing law.** The slope of cycle thickness against
depth was tried several ways (along rays, per band, from boundary density). In
2D, H2's rings break into spots inward, and the spot boundaries hide the
widening. In a round cavity it shows weakly (+0.45, r² 0.2); in the angular
nodule its sign flips. It is not a reliable discriminant here.

## Results through photos (synthetic, 760 px, two seeds, JPEG 95 and 75)

- **Ring closure survives.** H1 reads 0.77–0.97 and H2 0.09–0.23, a clear
  separation.
- **Corners do not survive.** The traced outline first had to be simplified:
  its pixel steps gave 32 false 135° corners and none of the six true ones,
  which is now fixed and tested. After that, the photo values are H1 1.13–1.47
  against H2 1.31–1.71. They overlap, because the band tracing (ADR 0012) rounds
  corners itself: its growth-order field blurs across the bisector.
  - A finer orientation scale didn't help.
  - Neither did doubling the photo and analysis resolution (H1 1.13, H2 1.59).

  So the rounding comes from the method, not from pixels.
- **The floor-width law does not survive.** The tracing over-splits layers
  (22–34 traced against 11), and the slopes scatter from −0.45 to +0.95.

## The owner's photos (analysed privately, nothing committed)

- Ring closure is 0.00–0.16 on all eight. Read naively, that would point to H2.
  But synthetic photos of a known H1 agate give 0.77–0.97, so the low values
  come from the real-photo tracing: natural bands are interrupted by quartz,
  cracks and changes of tint. They are **not** evidence for a mechanism.
- Corners can't be measured on these natural outlines.
- The floor-width law on slab-2 gives no meaningful fit (r² 0.09).

## Consequences

- No mechanism verdict is given for a specimen photo yet. The bottleneck is
  band tracing on real photos, not the discriminants.
- **Next in M10:**
  - a corner measure independent of band tracing, comparing raw colour profiles
    along the bisector and the edge normal, which needs a raw-appearance field;
  - layer tracing that doesn't over-split;
  - validating real-photo tracing against hand-marked bands on the owner's
    photos, which needs the owner's help;
  - then simulation-based inference, and quartz and inclusion detection.
