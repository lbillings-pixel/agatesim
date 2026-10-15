# 17. H1 without the boundary-layer approximation: what survives

- Status: accepted
- Date: 2026-10-15
- Builds on: [ADR 0013](0013-mechanistic-front-feedback.md), [ADR 0015](0015-mechanistic-liesegang.md)

## Context

H1 (ADR 0013) keeps fortification's sharp corners by assumption. Its front
state is the same all along the front, the boundary-layer approximation. H2
(ADR 0015) loses corners for real. The fair test is to run H1 with explicit
diffusion of silica and impurity in the cavity, and see whether its corners
survive.

## What was done, and found

1. **The boundary-layer oscillator is inconsistent with explicit diffusion.**
   - The oscillation of ADR 0013 needs slow silica resupply (ε ≈ 0.002–0.01).
     With explicit diffusion, slow resupply means a thick silica layer, √(D_s/ε)
     boundary-layer thicknesses deep.
   - The front crosses that layer faster than diffusion rebuilds it: the silica
     Péclet number is about 9–25. The depletion stays near 10%, and there is no
     feedback and no rhythm.
   - The 0D model assumed a layer that keeps pace with the front.
2. **Physical front conditions.** The model was reformulated with moving-front
   (Stefan) conditions and explicit diffusion in the front's frame
   (`scripts/h1_stefan_scan.py`):
   - silica is taken into the solid (flux q·U);
   - impurity is rejected (flux (1 − K)·U·a).
3. **Oscillations exist, but rarely.** 4,000 random parameter sets were scanned
   on the GPU, with diffusivities kept physical (silica 0.3–3× the impurity):
   - 15 oscillated at 200 cells;
   - only 2 also oscillated at 100 and 400 cells. The rest were numerical
     artefacts, including the set first chosen.

   So converged oscillations occupy about 0.05% of the sampled space. Both
   converged sets:
   - are stick-slip: the front stops, then restarts;
   - have a silica Péclet number below 1;
   - need switch-like catalysis (n = 4, β ≈ 200).
4. **The bands are micro-bands.** The converged cycles are 0.14 and 0.39 impurity
   screening lengths long, far thinner than the diffusion length. If that length
   were about 10 µm, the bands would be 1–4 µm: the scale of agate's
   micro-banding behind iris colours ([@cartwright2026] §5.1.1), not of its
   visible bands. This is a scale argument within the model, not evidence.
5. **2D (not concluded).** A level-set version was written: an upwind narrow band
   with distance re-initialisation, exact to about one cell on a test disc. At a
   resolved lattice (screening length 20 cells), a converged set did not
   oscillate. It settled into slow steady growth, while the same set
   stick-slips in 1D. The limit cycle evidently depends on how the moving
   boundary is discretised (a flux at a boundary node in 1D, a volumetric sink
   in the first cell in 2D). The 2D solver was not committed. Whether H1's
   corners survive explicit diffusion remains open.

## Decision

- The H1 verifications of ADR 0013 stand as **boundary-layer-approximation**
  results. The registry entry is unchanged, and this ADR records their limits:
  - the regime used is inconsistent with explicit diffusion;
  - with physical front conditions, oscillation is rare, stick-slip and
    micro-scale.
- The scan script is kept, so the result can be reproduced and extended
  (`uv sync --extra gpu`).

## Consequences

- For the corner question, H1 is no longer a clean counterpart to H2. Its sharp
  corners rest on an approximation whose oscillating regime does not survive
  explicit diffusion. H2's rounded corners are a solved result.
- **Open, in order of value:**
  - a 2D front scheme that reproduces the 1D stick-slip cycle (a sub-cell flux
    boundary at the level set), then the corner test;
  - whether stick-slip H1 gives the 0.5–5 µm micro-zonation of iris agate;
  - other H1 feedbacks, such as impurity inhibition ([@torii2024]).
