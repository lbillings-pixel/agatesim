# 82. H1's stain is scaled over the run, not over the points

- Status: accepted (owner, 2026-11-10: audit decision C33, approved for this session)
- Date: 2026-11-10
- Builds on: [ADR 0013](0013-mechanistic-front-feedback.md) (H1 front feedback),
  [ADR 0048](0048-shadow-agate-by-a-stated-milkiness-link.md) (milky and clear bands),
  [ADR 0021](0021-three-dimensional-runs.md) (3D runs: models evaluated at points)
- Audit: PR #14, items B2.6 and C33

## Context

H1 (front feedback) colours chalcedony by the impurity it incorporated, on a log
scale from 0 to 1. The ends of that scale were the lowest and highest values among
the points being evaluated at that moment. In 2D those are the run's pixels, so
the scale depended slightly on the resolution, against ADR 0013's "the result
doesn't depend on resolution". In 3D a cut or volume is evaluated in batches of
points, so a point's colour depended on which other points shared its batch: one
point alone got no stain at all. That blocked the audit's fix B2.6 (evaluate cuts
in chunks, to bound memory), because chunked cuts came out different.

The milky/clear threshold and the band edges already used the run's history
(the midrange over all chalcedony samples), and so do trace pigments
([ADR 0050](0050-pigments-and-a-palette.md)).

## Decision

1. The stain's scale runs from the lowest to the highest incorporated impurity over
   the run's chalcedony history: the same samples `milky_level` uses. A point's
   fields now depend only on its wall distance and the run.
2. Cuts are evaluated in chunks of up to 2^21 points (whole rows), like volumes
   (B2.6).

## Consequences

- Only `impurity` changes, and only in H1 presets: 12 2D presets and 9 3D presets'
  default cuts (160 px). Phase, bands, milky/clear, timing and pigments are
  bit-identical. In 19 of the 21 the stain moves by at most 0.004 on its 0 to 0.6
  scale. In 2D `stick-mechanistic` (a thin seam, whose pixels at 160 px missed part
  of the run's range) it moves by up to 0.12, mean 0.013: a mean colour change of
  2 in 255, barely visible. In `eye-mechanistic-3d` a few pixels move by up to
  0.06 (mean 0.0007). The gallery is unchanged to the eye, so not regenerated.
- A 2048 px cut of `fortification-mechanistic-3d` peaks at 388 MiB instead of
  526 MiB, in the same time (7.6 s); the saving grows with the cut's size.

- A test checks that points take the same values alone or together, and one that a
  cut evaluated in small chunks equals one evaluated whole.
