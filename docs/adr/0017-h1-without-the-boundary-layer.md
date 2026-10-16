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

## Amendment (2026-10-16): no oscillation at all; findings 3–5 were artefacts

The corner test started by checking that a 2D scheme reproduces the 1D
stick-slip cycle of the two "converged" sets. Neither cycle survived a careful
check:

- **The reference isn't converged.** In the front-frame solver, set 0's cycle
  drops from 0.13 to 0.06 screening lengths between 200 and 400 cells, which is
  less than one cell either way. Its peak speed falls from 0.74 to 0.41.
- **A second, independent scheme agrees.** This one is lab-frame and cut-cell:
  the front crosses a fixed grid, the front cell is balanced exactly, and front
  values are reconstructed from the flux conditions. Its oscillations also
  shrink as the grid is refined. Set 1 swings over 0.18–1.10 at h = 0.1 but only
  0.39–0.64 at h = 0.05, and the residual wobble's period is the time to cross
  two cells (U × period = 2h).
  - Both schemes give the same mean front speed (0.127 and 0.44).
- **Exact linear stability** (`scripts/h1_linear_stability.py`):
  - **Method.** Steady fronts have exponential profiles. A disturbance
    ∝ e^(λt) gives a scalar characteristic function Φ(λ) with no grid, and its
    zeros in Re λ > 0 are counted by the argument principle.
  - **Checks.** Φ(0⁺) equals dG/dU − 1 to five digits. The steady speeds equal
    both solvers' mean speeds.
  - **The two sets.** Both are strongly stable (|Φ| ≥ 31 throughout the plane
    near the axis).
  - **All 4,000 sets of the original scan.** None has an oscillatory
    instability. Five are bistable, with three steady fronts each, and their
    one unstable state is the middle branch, with a real root.

So H1 with explicit diffusion and moving-front conditions **doesn't
self-organise bands** anywhere in the sampled space. Findings 3–5 above were
artefacts of discretising the moving front, and the micro-band scale argument
(4) falls with them.

**The corner test is moot for this formulation.** A front without bands has
no band corners to keep. H1's fortification and seam verifications (ADR 0013)
rest entirely on the boundary-layer approximation, whose oscillating regime has
no counterpart once diffusion is explicit. The registry still records them as
verified, with this caveat. Changing that is the owner's decision.

**What could restore banding.** The boundary-layer model oscillates because
its lumped layer stores impurity and responds with a delay. With explicit
diffusion, the front has no store of its own. A physical candidate is an
interface state with its own kinetics, such as impurity adsorbed on the growth
surface that catalyses or inhibits growth ([@torii2024]). The exact analysis
extends to it at little cost: one more equation at the front.

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
