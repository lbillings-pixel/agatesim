# 81. Plume reach from the wall

- Status: accepted (owner, 2026-11-09: "Let's fix it!", on quartz islands in a plume
  stone's cavity; agatesim work granted for the session from Nodule)
- Date: 2026-11-09
- Builds on: [ADR 0025](0025-inclusions-in-3d.md) (3D aggregation),
  [ADR 0080](0080-slow-band-growth-round-plumes.md) (slow band growth round plumes),
  [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule needs)
- Spec: Nodule's ADR 0018 section 13

## Context

With slow growth round plumes (ADR 0080), a Nodule stone with a quartz-lined open centre
kept its centre, but a plume that rose close to it still caused trouble: its coat
bulged past the point where the wall's bands leave the centre, quartz grew on the bulge,
and the cut showed quartz islands inside the open cavity and a tongue of coat rings
curling into the centre. In 3D nothing floated: quartz was one body, and chalcedony with
the plumes another. A dendrite stage could limit where plumes start (start height) but
not how far they grow.

## Decision

1. **`dendrite_reach_mm`** (3D, `effective`, default 0 = anywhere): lattice cells farther
   than this from the cavity wall are not free, so particles neither walk nor stick
   there and plumes stop within reach. Only the aggregation's input mask changes; the
   GPU, compiled and NumPy loops are untouched (ADR 0057/0061 parity holds).
2. The share `dendrite_amount` stays a share of the free space, so a reach also lowers
   the total plume material in proportion.
3. **Assumption:** a hard limit at one distance from the wall. No source gives how far
   plumes reach; Kile reports plumes typically 1-2 inches long, up to 5 [@kile2002,
   p. 259] (*plausible*). Nodule sets the reach from each stone's chalcedony thickness and
   wrap rate.

## Consequences

- Default results are byte-identical: cuts of plume-3d and moss-3d at 256 px (two planes
  each) hash the same before and after (measured 2026-11-09).
- In the Nodule stone (reach 9.0 mm against 12.7 mm of wall growth before quartz), the
  quartz islands and the tongue are gone and the cavity's edge is clean; build 14 s.
- Test (tests/test_volume_dendrites.py): with a 4 mm reach on plume-3d, every inclusion
  point lies within 4.6 mm of the wall. Negative control: without a reach, some do not.
- 2D models ignore the setting.
- Procedural only: nothing here is evidence for how far plumes grow, or why.
