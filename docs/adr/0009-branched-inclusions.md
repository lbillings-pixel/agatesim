# 9. Branched inclusions: moss and plume agate

- Status: accepted
- Date: 2026-10-15

## Context

M5 targets moss (dendritic) and plume agate. A literature pass before modelling
(science notes §6) found that "moss agate" covers two different things:

- dendrites of Mn or Fe oxides, explained either by aggregation of diffusing
  particles (DLA-like; [@chopard1991], [@hou2023]) or by solidified fingers of
  infiltrating fluid ([@garciaruiz1994]);
- green filaments with Fe-silicate cores wrapped in concentric chalcedony,
  possibly with a biological template ([@goetze2020b]).

Plume agate is interpreted as a silica garden, where osmosis, reaction and
buoyancy make growth directional ([@goetze2020] §5.5). The owner chose
DLA-style growth on a world-scale lattice, and a scheduled dendrite stage that
later chalcedony encloses.

## Decision

1. **A scheduled `dendrite` condition.** At 0.5 or above, the stage grows
   inclusions instead of silica. Its mode takes precedence over all other modes.
   Later stages treat inclusions as solid surfaces, so chalcedony grows around
   every branch, as in the filament-plus-crust structure reported for moss
   agate.
2. **Multi-particle DLA** (`agatesim.models.dendrites`). Particles random-walk on
   a lattice whose cell is the finest branch width, and stick to touching
   branches with probability `dendrite_sticking`. Branches start from blue-noise
   points on the growth surface, spaced `dendrite_spacing_mm` apart. A steady
   concentration `dendrite_density` is kept, replenished until a total
   `dendrite_amount` has been released. Concentration sets bulkiness and amount
   sets size: higher concentration gives bulkier dendrites ([@hou2023]). Branches
   compete for particles, so fewer reach farther from the wall, which is tested.
3. **Plumes** use an upward bias, `dendrite_upward`. A particle sitting on top of
   a branch sticks with the full probability, while one at the side or below
   sticks less readily. Inclusions then grow upward against gravity. This is a
   procedural stand-in for buoyancy-driven growth, not a model of a silica
   garden. `dendrite_start_height` restricts the starting points to the lower
   part of the cavity. A first attempt, drifting the particles downward, built a
   dense crust on the floor instead of rising plumes, and was dropped.
4. **Resolution independence.** The lattice is in world coordinates with a fixed
   cell size, and every draw is made on it. Inclusions are rasterised by "any
   cell in the pixel, or the pixel's centre in a cell", so thin branches stay
   connected at preview resolution. The first stage, which doesn't depend on the
   grid, is cached in-process, so previews don't regrow it. A test checks that
   the cache never changes a result.
5. **Inclusion tint.** For inclusion pixels, `impurity` holds the mineral tint:
   0 = green Fe-silicate, 0.5 = red-brown Fe oxide, 1 = black Mn oxide. Tube
   cores now render green, matching the Fe-silicate cores reported for
   filaments.
6. **Criteria.**
   - **moss:**
     - `fractal-dimension`: the area-weighted box-counting dimension of each
       inclusion at least 2 mm across, measured on its own, must lie in
       [1.3, 1.9]. Measuring each inclusion separately keeps parallel lines from
       passing.
     - `translucent-matrix`: inclusions take at most 20% of the cavity.
   - **plume:**
     - `anisotropic-growth`: mean cos² between branch direction and gravity, from
       the structure tensor, must be at least 0.7. Branches pointing every way
       give about 0.5.
     - `encapsulated`: at least 98% of inclusion pixels have no open space within
       2 px.

   These replace provisional criteria that had no thresholds. Negative controls
   cover banding without inclusions, tubes, straight filaments, massive
   inclusions, moss dendrites judged as plumes, and plumes left in open space.

## Consequences

- The timeline editor gains *Dendrite growth*, and the parameter panel gains the
  dendrite parameters, all automatically.
- Simplifications to revisit:
  - The procedural dendrites measure about 1.45. Natural agate dendrites still
    need a measured range from a full-text source.
  - Only dendrites that grow into open space, before the chalcedony, are
    modelled. Dendrites that grow later along fractures or in a gel
    ([@monecke2023]), and viscous fingering, are not.
  - Branches follow a square lattice, which shows at high zoom.
  - The DLA runs in Python and takes about 1–2 s per new dendrite stage. A
    compiled or GPU kernel belongs in M8.
