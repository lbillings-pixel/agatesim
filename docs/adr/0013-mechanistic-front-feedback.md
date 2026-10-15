# 13. First mechanistic model: front feedback (H1)

- Status: accepted; limits recorded in [ADR 0017](0017-h1-without-the-boundary-layer.md): the oscillating regime used here doesn't survive explicit diffusion
- Date: 2026-10-15
- Builds on: [ADR 0003](0003-model-architecture.md), [ADR 0005](0005-verification-tiers-and-parameter-natures.md)

## Context

M8 starts the mechanistic tier with hypothesis H1: bands that self-organise
from feedback at the crystallisation front, without an external rhythm
(docs/science/mechanisms.md §4).

The literature pass found:

- The Wang–Merino equations themselves are in closed-access papers [@wang1990]
  [@merino1995]. A review gives the mechanism's core: Al³⁺ accumulating at the
  front accelerates crystallisation [@cartwright2026].
- The Wang–Merino model is known to have periodic solutions, with bifurcation
  values and a catalogue of phase portraits; zone widths per cycle were
  estimated [@halden2000] (abstract only).
- Wang and Merino introduced the boundary-layer approximation for zoned
  crystals: a thin solution layer at the front exchanging with a well-mixed
  bulk. Later oscillatory-zoning models of growth from solution also use it
  [@kalischewski2006].
- Intrinsic oscillatory zoning in general arises from feedback between growth
  and composition, for example growth rate against the partition coefficient
  [@cartwright2026] §4.1.6.

## Decision

1. **A generic H1-family model, not a reproduction of Wang–Merino.**
   `mechanistic-front-feedback` (`agatesim.models.front_feedback`) keeps
   their ingredients: a boundary layer at the front, with silica that growth
   consumes and an impurity that the front rejects and that accelerates growth
   once gathered. Its equations are our own. Every parameter is `effective`.
   - Velocity: v = s (1 + β aⁿ / (a_cⁿ + aⁿ)).
   - Silica balance: ds/dτ = ε((s_b − s) − γ v).
   - Impurity balance: da/dτ = (a_b − a) + λ v (1 − K(v)) a, with solute
     trapping K(v) = (k₀ + v/v_t)/(1 + v/v_t).
2. **When it oscillates.** A linear stability analysis and a parameter scan
   show limit cycles only when:
   - silica resupply is slow (ε ≪ 1);
   - the rejection rate is bounded, λ v_t (1 − k₀) < 1;
   - catalysis is switch-like.

   Random sampling of the plausible ranges found oscillations in 0.015% of
   parameter sets at n = 2, 0.9% at n = 4 and 1.8% at n = 8. The default
   parameters lie near the onset of oscillation (Hopf), so a cycle's fast,
   impurity-rich half is nearly as thick as its slow half. Relaxation-type
   cycles further from onset give a thin impurity-rich band and a thick
   impurity-poor one.
3. **Geometry from the boundary-layer approximation.** The front's state is
   the same all along it, so the front advances inward along the exact wall
   distance at speed v·δ (δ is the boundary-layer thickness, the model's
   length scale). Corners stay sharp, as they do in agate. This is an
   assumption of the approximation, not a result: the model doesn't test
   whether cavity-scale diffusion would round corners. A full 2D diffusion
   field is the way to test that (with H2).
4. **Open or closed cavity.**
   - Open (`silica_inventory` = 0): the bulk is resupplied and stays constant.
   - Closed: silica falls as the cavity fills, s_b = (1 − F/F*)/(1 − F). Rejected
     impurity builds up, a_b = (1 − I)/(1 − F). Below `quartz_below`, quartz grows
     instead of chalcedony ([@goetze2020] §6), and growth stops when silica runs
     out.
5. **Fields.**
   - Bands are the half-cycles: crossings of the incorporated impurity through
     the midrange of its log over the run.
   - The incorporated impurity is the iron stand-in.
   - Impurity-rich bands render milky. This is an assumption: H1 pairs
     trace-element-rich bands with twisted fibres [@merino1995].
   - Nothing is random, and the result doesn't depend on resolution.
6. **Verification (mechanistic tier).**
   - `fortification-mechanistic` passes: wall-parallel 0.998, corners 0.45,
     closed bands 0.94, 37 bands.
   - `seam-mechanistic` passes: mirror symmetry 0.99, central suture 0.011.
   - Both use the open cavity.
   - Negative controls: with linear catalysis (n = 1), fast silica resupply
     (ε = 0.5) or no catalysis, only a few bands form, and band-count fails.
   - Verified presets are named `<archetype>-mechanistic`, and a test enforces
     this.

## What verification means here

The mechanistic tier shows that this mechanism *can* produce the form. It is not
evidence that agates form this way (ADR 0005). Specifically:

- The band rhythm emerges from the dynamics.
- The fortification geometry (wall-parallel, sharp corners, closed rings)
  follows from the uniform-front assumption, which is shared with the
  procedural model.

## Consequences

- **The closed cavity is fragile.** Impurity rejected into a closed cavity
  builds up as 1/(1 − F) and moves the system out of its oscillating range after
  a band or two. Agate profiles do show a gradual accumulation trend in trace
  elements [@halden2000], but in this model the oscillation doesn't survive it.
  Open-system resupply, or a wider oscillating range, is needed. This is a
  property of the model worth testing against measured trace-element profiles.
- **The rhythm is too regular.** An open-system limit cycle gives bands that
  vary by under 10%. Natural sequences are irregular, and nearby agates differ
  [@cartwright2026]. Noise in the supply, or chaotic regimes, are candidates.
  So is a second impurity.
- **Next in M8:**
  - H2: 2D reaction–diffusion with nucleation (Liesegang type), on a GPU backend
    (CuPy with a NumPy fallback).
  - The same 2D diffusion field can carry H1 without the uniform-front
    assumption.
  - H4: mechanistic settling.
