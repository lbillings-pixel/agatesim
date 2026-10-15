# 15. Mechanistic Liesegang precipitation (H2), and a hypothesis test

- Status: accepted
- Date: 2026-10-15
- Builds on: [ADR 0013](0013-mechanistic-front-feedback.md)

## Context

H2 holds that agate's colour bands are Liesegang-type precipitation. A
metal (for example iron) diffuses from the host rock into a silica gel and
precipitates in rhythmic bands. The reviews consider it out of favour for agate
([@moxon2020] §5, [@goetze2020] §5.4). One review gives a specific reason: Liesegang
patterns lack agate's sharp corners, show ring defects, and follow a spacing
law that agates don't ([@cartwright2026] §5.1.1). These are testable claims, and
the fortification criteria already measure corners.

## Decision

1. **Model** `mechanistic-liesegang` (`agatesim.models.liesegang`, solver in
   `agatesim._rd`). It uses pre-nucleation kinetics ([@cartwright2026] §4.1.5):
   - A enters through the wall from a reservoir and meets B in the gel.
   - They react to a dissolved product C, which nucleates above c_n.
   - C keeps precipitating above its solubility c_s where precipitate exists.
   - C spreads into a neighbouring cell where the solution exceeds c_sp
     (c_s < c_sp < c_n).

   Every parameter is `effective`.
2. **Why spreading.** Without it, each nucleus drains its neighbours, and
   precipitate sits on single lattice cells (speckle in 2D; one-cell bands in
   1D). If spreading starts at c_s, the gel precipitates continuously. With an
   intermediate c_sp, the 1D kinetics reproduce both Liesegang laws: band
   positions in a geometric series (successive ratios falling from about 1.36
   to 1.18), and widths growing with position.
3. **A fixed lattice.** The kinetics run on a lattice with a set spacing in
   millimetres (`lattice_mm`, which sets the length scale), then are sampled to
   the output grid. So previews show the same bands as full runs, and a test
   checks this.
4. **Bands** are the switches between precipitate and clear gel, in order of
   the reaction front's arrival. Slivers holding under 0.5 mm² join their
   neighbours. The precipitate is the iron stand-in.
5. **Backend.** The solver takes an array module: NumPy, or CuPy on the GPU when
   `AGATESIM_GPU=1` and CuPy is installed (`uv sync --extra gpu`: cupy-cuda13x with
   NVIDIA's CUDA libraries from PyPI). On CuPy, each time step is one fused CUDA
   kernel. The generic array code was launch-bound at 2.3 ms per step whatever
   the size. A test compares GPU and CPU results when a GPU is present.

   | Case (RTX 4070) | NumPy | CuPy, generic | CuPy, fused |
   |---|---|---|---|
   | 15 mm nodule, 0.04 mm lattice | 36 s | 22 s | 0.5 s |
   | 50 mm nodule, 0.05 mm lattice (0.5 M cells) | about 2 h (est.) | 155 s | 12 s |
   | 30 mm seam, 0.02 mm lattice | 806 s | | 2.6 s |

   CI has no GPU, so it runs the small cases on NumPy.

## Result: the hypothesis test

On a 15 mm angular nodule (0.04 mm lattice), the Liesegang bands are:
- wall-parallel (0.97);
- closed (8 of 8 rings at 512 px);
- in growing cycles (0.51, 0.65, 0.90 mm);
- but they **round off the corners**. The turn width over band spacing is 1.6–2.4
  per corner, against the 0.7 threshold.

The front-feedback model (H1) scores 0.45 on the same criterion. This is a test
in the suite.

At full size on the GPU (50 mm nodule, 0.05 mm lattice):
- Corners are 2.3–4.0 per corner (the criterion caps at 4).
- Only 20 of 125 bands are closed rings. Inward of about a third of the depth,
  the rings break into rows of spots. This is the 2D instability of Liesegang
  rings, and the review counts such ring defects as un-agate-like
  ([@cartwright2026] §5.1.1).

So, within our models, Cartwright's corner argument holds quantitatively.
Precipitation controlled by diffusion through the cavity rounds corners. Growth
controlled locally at the front keeps them. Two cautions:
- H1 keeps corners by assumption, its uniform-front approximation (ADR 0013).
- Corner rounding in H2 increases inward, so small cavities with few bands
  score near the threshold.

H2 therefore **does not** verify fortification at the mechanistic tier, and
the registry records nothing for it. Sharp-cornered fortification counts as
evidence against H2 *as modelled here*.

**Seam (30 mm, GPU).** Mirror symmetry passed (0.98). The central suture failed
(0.29), so the seam isn't verified either. Why the last-reached material sits
off the midline in some sections is not yet diagnosed.

## Consequences

- **Two concrete discriminants against specimens:**
  - corner sharpness;
  - band spacing: Liesegang cycles widen inward geometrically.

  The sequence statistics of ADR 0014 can measure spacing trends on the
  owner's photos.
- **Realistic cavities need the GPU.** In the app, a preview of this model on
  the CPU can take minutes; with the GPU it takes seconds.
- **Still to do:** diagnose the seam's suture; Cahn–Hilliard (post-nucleation) ripening
  as a variant [@liu2025]; and H1 run inside the same 2D diffusion field,
  without the uniform-front assumption.
