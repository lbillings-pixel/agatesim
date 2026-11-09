# 80. Slow band growth round plumes

- Status: accepted (owner, 2026-11-09: chose this option, "B", and granted agatesim work
  for the session from Nodule)
- Date: 2026-11-09
- Builds on: [ADR 0025](0025-inclusions-in-3d.md) (3D aggregation; later bands line the
  inclusions), [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule
  needs), [ADR 0079](0079-plumes-traced-tilted-tinted-and-haloed.md) (plumes traced)
- Spec: Nodule's ADR 0018 section 13

## Context

In 3D, every later band grows round a dendrite aggregate as fast as it grows from the
wall: the aggregate joins the growth solid with the wall's offset. Nodule placed plumes
before the bands of its mock-up stones. A plume that reaches into the cavity then sends
out rings as thick as the wall's bands, which fill the centre long before the wall's
bands meet: no quartz-lined plume stone on Nodule's look sheet showed its quartz or open
centre (one measured: 118 mm² of cavity and quartz on the cut without plumes, none with
them; another shows none even without plumes), and each plume crossed by the cut carried
its own set of rings,
reading as orbicular agate. The sources say plumes and moss are engulfed by later bands
[@akahane2025] and commonly enclosed by clear halos
[@kile2002, pp. 259, 263] (*plausible*), but give no rate for growth round them.

## Decision

1. **`dendrite_wrap_rate`** (3D, `effective`, default 1, range (0, 1]): later bands grow
   round a dendrite stage's aggregate at this share of their growth from the wall. The
   growth solid keeps, for each inclusion, its growth since it formed (at the wall's
   rate) and this rate; its distance in the open space is the inclusion's distance over
   the rate, less that growth. A coat round a plume is therefore rate x the wall's
   growth thick, and its bands are thinner by the same share.
2. Sticks and the fronts model's inclusions keep rate 1 (no change).
3. **Assumption:** one rate for every plume and every band of a stone, constant in time.
   No source gives one; the value is chosen for the look (Nodule uses 0.15).

## Consequences

- Default results are byte-identical: cuts of plume-3d and moss-3d at 256 px (two planes
  each) hash the same before and after (measured 2026-11-09). At rate 1 the arithmetic
  is unchanged (division by 1).
- Measured on plume-3d at 1 M cells: coat growth over wall growth, median over chalcedony
  0.5-1.5 mm from a plume and over 8 mm from the wall, is 1.19, 0.59, 0.35 and 0.18 at
  rates 1, 0.5, 0.3 and 0.15 (it tracks the rate; the excess is the time steps' rounding).
  In a Nodule stone with a quartz-lined centre, rate 0.15 kept 54 of 58 mm² of cavity and
  64 of 60 mm² of quartz on the cut, rate 0.3 only 22 mm² of cavity.
- Test (tests/test_volume_dendrites.py): at rate 0.15 that median is under 0.5 (thin
  coats). Negative control: at the default rate it is not.
- Distances near a slowly wrapped plume are in units of wall growth, so the wobble's taper
  and wall features read them as such; only the coat's own thickness changes.
- 2D models ignore the setting.
- Procedural only: nothing here is evidence for how plumes are engulfed.
