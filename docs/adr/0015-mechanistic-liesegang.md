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
   `AGATESIM_GPU=1` and CuPy is installed. A test compares the two when a GPU is
   present. Runs are slow on the CPU: a 15 mm nodule takes about 40 s, and a
   60 mm seam about 13 minutes.

## Result: the hypothesis test

On a 15 mm angular nodule (0.04 mm lattice), the Liesegang bands are:
- wall-parallel (0.97);
- closed (8 of 8 rings at 512 px);
- in growing cycles (0.51, 0.65, 0.90 mm);
- but they **round off the corners**. The turn width over band spacing is 1.6–2.4
  per corner, against the 0.7 threshold.

The front-feedback model (H1) scores 0.45 on the same criterion. This is a test
in the suite.

So, within our models, Cartwright's corner argument holds quantitatively.
Precipitation controlled by diffusion through the cavity rounds corners. Growth
controlled locally at the front keeps them. Two cautions:
- H1 keeps corners by assumption, its uniform-front approximation (ADR 0013).
- Corner rounding in H2 increases inward, so small cavities with few bands
  score near the threshold.

H2 therefore **does not** verify fortification at the mechanistic tier, and
the registry records nothing for it. Sharp-cornered fortification counts as
evidence against H2 *as modelled here*.

**Seam (one run, before the band-labelling fix).** Mirror symmetry passed
(0.98). The central suture failed (0.29), so the seam isn't verified either. It
should be re-run on the GPU.

## Consequences

- **Two concrete discriminants against specimens:**
  - corner sharpness;
  - band spacing: Liesegang cycles widen inward geometrically.

  The sequence statistics of ADR 0014 can measure spacing trends on the
  owner's photos.
- **The GPU backend is needed for realistic cavities** (50 mm at a 0.05 mm
  lattice). CuPy needs the CUDA 13 toolkit, either installed locally or as
  NVIDIA's PyPI packages. That installation waits for the owner's approval.
- **Still to do:** a fused GPU kernel; Cahn–Hilliard (post-nucleation) ripening
  as a variant [@liu2025]; and H1 run inside the same 2D diffusion field,
  without the uniform-front assumption.
