# 91. The chalcedony's last surface, returned for rendering beside the crystal wall

- Status: accepted (owner, 2026-11-19 late: approved from Nodule that agatesim expose
  the lining stage's level beside `CrystalWall`, sharing `evaluate`'s code, with push
  and pin move; the refusal below for deep channels is Claude's choice after measuring,
  reported to the owner)
- Date: 2026-11-19
- Builds on: [ADR 0090](0090-the-crystal-wall-for-rendering.md) (the crystal wall),
  [ADR 0077](0077-wall-features-clear-layer-and-channels.md) (wall channels)
- Spec: Nodule's ADR 0019 s.6.12, step 3 ("Option A probe" and the owner's verdict)

## Context

Nodule draws a geode's hollow as air. Where the crystals do not cover the wall, the
air meets bare chalcedony, and the crystal wall's `level` cannot place that surface:
it is also positive on much of the chalcedony behind the sites (ADR 0090). Nodule's
probe found the surface as a second, smooth level: the stage before the crystals, when
it is lining, fills a point when its distance (the clamped solid distance, plus the
tapered wobble, plus the channel delay) is within its last reach, so that distance
minus the reach is positive exactly where the crystals start from open space. The
probe read `evaluate`'s closure to get it, which Nodule must not do in its source.

## Decision

- **The readout.** `CrystalWall` gains `chalcedony_level(points, inside)` (default
  None, so the positional constructor stands): the lining stage's distance minus its
  last reach, in mm. Positive exactly where the crystal stage's quartz or the hollow
  lies; smooth across the chalcedony's last surface, so a caller can sample it on a
  grid and read it trilinearly. Points outside `inside` or in a tube core read minus
  the reach (as at distance 0, so the value is continuous across the wall). Callers
  chunk it, as `evaluate`.
- **Shared code.** `prepare_growth` has one `lining_distance` that `evaluate`'s lining
  branch and the level both call, so the level cannot drift from the fill. The
  arithmetic is unchanged.
- **When it is None.** When the stage before the crystals is not lining (or there is
  none), and when earlier stages lie under that lining and the wall channels' stack
  (`channel_depth_mm`) is deeper than `CHANNEL_DEPTH_SHARE` (0.8, *effective*) of the
  lining's reach. A stack that deep reaches back into the earlier stages' material
  (spherulites, a first lining), which the lining's own distance reads as open; those
  points were filled before the lining and `evaluate` never asks the lining about
  them. A caller then falls back to its own test (Nodule: its gate).
- **Rejected:** taking the minimum with the solid's distance at the lining's start. It
  cut the false open points but not to zero (the solid's balls leave out the
  spherulites' wobble) and lost true ones where a first lining's own channel delay left
  more open than the solid records (about 5 % of the open points).

## Measured

Sign of the level against the stage's quartz by grain or VOID, on 150 000 to 210 000
random inside points per run (Nodule's `runs/hollow-air/phi_sign_check.py`):

- Exact (0 wrong) on the quartz geode, the geode with two channels, with channels and
  tubes, lining with a stack 0.95 of it, and spherulites, lining, crystals with stacks
  0.6, 0.8 and 0.9 of the lining, and lining, spherulites, lining with a stack 0.37
  of the last lining; also on all 11 crystal stones of Nodule's sheets 0-11
  that have channels and an earlier stage (stacks 0.25-0.65 of the last lining).
- Wrong with earlier stages and a stack at or past the lining: 12 points at 1.0, 153 at
  1.03 (spherulites first); 1 613 (about 4 % of the open points, up to 1.6 mm from
  them) at 1.85 (lining, spherulites, lining). Hence the 0.8 limit, a margin below the
  last exact case (*plausible*: one stone shape, a few ratios).
- Cost: 1.8-2.7 µs a point on one CPU core, peak 57-230 MiB in chunks of 200 000.

## Tests (tests/test_crystal_wall.py)

- The level is positive exactly where crystals start open on the geode with channels
  and tubes, with a stack 0.95 of the lining, and with spherulites first at stacks 0.6
  and 0.79. Control: a surface 0.3 mm off disagrees.
- Control: the plain wall distance minus the reach (no wobble, no channel delay)
  disagrees; tube cores read negative.
- None for spherulites-first and lining-spherulites-lining with a 5 mm stack, and for
  spherulites straight into crystals; kept for a deep stack over the bare wall.
- Fields unchanged: every Fields array hashes the same before and after on four runs
  (geode, geode with channels, a channel stone without crystals, lining-spherulites-
  lining-crystals with channels; Nodule's `runs/hollow-air/phi_baseline.py`).

## Consequences

- Nodule moves its pin and samples the level on a 0.1 mm grid near the surface for its
  void box; where it is None, the void box keeps its current gate.
- If Nodule ever draws channel stacks deeper than 0.8 of the last lining over earlier
  stages, those stones fall back; an exact level there would take each earlier stage's
  own fill test, a separate change.
