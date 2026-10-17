# 31. Eyes cut through the side of the dome

- Status: accepted (owner approved, 2026-10-16)
- Date: 2026-10-16
- Amends: `wall-nucleated` (eye), last changed by [ADR 0024](0024-eye-and-geode-tests-on-cuts.md)

## Context

After ADR 0024, a growth centre counts as an eye rooted at the wall if it lies
on the cavity wall (a cut through the nucleation site) or if its rings close
around it with no seed inside (a cut along the wall, showing a bullseye). Only
30% of random cuts through `eye-3d` passed. Most failures are cuts through the
side of an eye's dome: its rings are arcs, centred near the cut's outline but
not on it, so neither rule applies. ADR 0024 left the rule for such arc systems
as a further decision.

## Decision

A growth centre off the wall whose rings don't close also counts as an eye
rooted at the wall when:

- it lies within 0.75 of its own curvature radius (the median radius of
  curvature of the rings voting for it) from the wall; and
- no seed (inclusion phase) lies within half that radius (rings around a seed
  are tubes, as before).

The threshold (0.8 of centres) is unchanged. `ARC_REACH = 0.75` in
`agatesim.criteria.botryoidal`.

**Why 0.75.** On 60 random cuts through `eye-3d` (384 px, seed 0), counting
centres up to a distance of 0.5, 0.75 and 1.0 times their radius would pass 62%,
77% and 85% of cuts, against 30% without the rule. A cut through the side of a
dome has arcs centred close to the outline compared with their size. A centre
deep in the cavity whose rings merely reach the wall sits about twice its
median ring radius from it. 0.75 keeps a clear margin from that.

## Results

- **2D verification preset still passes**: wall-nucleated 1.0 (6 of 7 centres
  on the wall, and one arc system near it).
- **Negative controls still fail**: tube agate 0 (every ring has a seed);
  fortification has no growth centres.
- **New negative control** (`tests/test_criteria.py`): eyes that nucleate late,
  on the inner surface of a thick wall lining (spherulitic stage at τ 0.5–0.65
  instead of 0–0.15), score 0 on wall-nucleated. With the stage at τ 0.3–0.45
  or 0.7–0.85 they score 0.2 and 0.
- **3D random cuts** (100, 512 px, seed 0, the protocol of ADR 0024): eye-3d
  passes 78% of cuts (30% before). The other two eye criteria pass on every
  cut (discrete-eyes and isolated-eyes 100%).

## Consequences

- Eye agate on random cuts now reads as eye agate far more often, as a
  collector would read it.
- The rule leans on the centre-finding of `growth_centres`; a centre found at
  the wrong place would be judged wrongly, as before.
