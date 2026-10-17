# 44. Plume agate as a silica garden

- Status: accepted
- Date: 2026-10-17
- Builds on: [ADR 0009](0009-branched-inclusions.md), [ADR 0035](0035-what-the-mechanistic-tier-requires.md), [ADR 0036](0036-mechanistic-moss.md), [ADR 0041](0041-reading-for-shadow-iris-and-plume.md)

## Context

Plume agate is interpreted as a silica garden ([@goetze2020] §5.5). The
procedural plume grows dendrites with a preference for sticking to branch
tops, a stand-in that ADR 0035 rules out at the mechanistic tier.

## Literature

From [@barge2015] (open review, read in parts) and [@cartwright2026] §4.3:

- A dissolving seed is wrapped in a semipermeable precipitation membrane.
  Osmotic pressure is released by rupture; buoyancy makes the lighter inner
  solution rise; the membrane keeps rupturing and re-precipitating where the
  two solutions meet. So the tube extends upward, with some sideways
  deviations. Osmosis and buoyancy drive the flow.
- With the inner solution supplied at a given rate, the tube's volume grows at
  that rate, which sets how fast it grows; its radius rises with the supply.
- Tubular structures in rocks are read as a slow geological version of
  chemical gardens. No model of plume growth in agate was found.

## Decision

1. **A chemical-garden stage** (`agatesim.models.gardens`;
   `order = "garden-wall"` in the staged model, then H1 encloses the tubes):
   - seeds on the cavity floor, where wall points face upward (dense grains
     settle there), spaced `spacing_mm` apart (blue noise on the exact wall);
   - each tip advances in 0.05 mm steps; buoyancy turns it back toward
     vertical (`buoyancy`, per mm), and it wanders sideways (`wander_deg`);
   - each seed's solution (`volume_mm2`, an area in the slab) is shared by all
     its tips, which grow together, and runs out after that much tube;
   - tips stop at the wall or at another seed's tube.
   All parameters are `effective` except the mineral (`tint`, `physical`).
2. **Linking assumption:** a membrane rupture (`rupture_per_mm`) starts a side
   tube at about 35°. The reading says membranes rupture and re-precipitate,
   but not that each rupture makes a branch; this is what gives the plumes
   their spray.
3. **Preset** `plume-mechanistic`: the procedural plume preset's cavity and
   seed; seeds 5 mm apart, 6 mm² of solution each, 0.4 ruptures per mm.
   Choosing effective values to make plumes about as tall as in photos is like
   choosing H1's boundary layer to set its band scale.
4. Every draw is per seed in world coordinates, so the tubes don't depend on
   the grid (a test). Not available in 3D yet (rejected with a message).

## Results

- `plume-mechanistic` passes at 768 px: anisotropic growth 0.93 (≥ 0.7),
  encapsulated 1.0 (≥ 0.98); at 384 and 256 px, 0.89 and 0.86.
- **Buoyancy is what makes them plumes:** with it off (and more wander) the
  tubes no longer grow upward, and anisotropic growth fails (0.49).
- Tubes start on the lower half of the cavity and rise more than 3 mm.

## Consequences

- Mechanistic tier: 10 of 12 forms. Pending: shadow (no sourced link from
  growth to milkiness) and iris (passes, but depends on shadow).
- The tubes are smooth stalks with side sprays, not the billowing, feathery
  plumes of the best specimens; finer branching would need a better account
  of rupture than the reading gave.
