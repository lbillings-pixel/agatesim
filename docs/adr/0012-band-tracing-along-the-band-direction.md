# 12. Band tracing along the photo's band direction

- Status: accepted
- Date: 2026-10-15
- Builds on: [ADR 0011](0011-specimen-analysis-first-pass.md)

## Context

ADR 0011 traced bands as patches of one colour class, joined by their distance
from the wall. That approach had two weaknesses. Bands broke into pieces wherever
their tint shifted along them (342 pieces for 36 true bands on a synthetic
botryoidal photo), and horizontal floor layers were ordered by wall distance,
which is wrong for them. Several fixes were tried and measured on the 28
synthetic validation photos: smoothing along the band, joining touching pieces
whose shared edge runs across the band, and more colour classes. Band counts
stayed 4–9 times too high, and no form but seam was ever confirmed.

## Decision

1. **Band direction.** The band normal at each pixel comes from the structure
   tensor of the colour gradients [@bigun1987]. The colours are extended
   outward first (each outside pixel takes its nearest inside colour), so the
   region's own edge isn't read as a band.
2. **Growth order φ.** A steady anisotropic diffusion, div(D grad φ) = 0, with
   D = (1 − ε) t tᵀ + ε I, t the band tangent and ε = 0.02 [@weickert1998]. Its
   level sets follow the bands.
   - φ = 0 on the stretches of wall that run parallel to the bands (judged 8 px
     inside the wall), with gaps up to about 28 px bridged (wall corners).
   - φ = 1 at the edge of the open space. On a filled face, φ = 1 on the deepest
     part (≥ 92% of the greatest wall distance): a point in a round nodule, the
     midline of a seam.
   - No flux across other walls, where bands meet the wall at an angle (floor
     layers against the side walls).
   - Each face's flux is scaled down where the two pixels differ in colour
     (exp(−(Δ/3 × median step)²), floored at 1%). A layer that ends against
     another band then doesn't take that band's order.
   - **Conservative (divergence-form) finite volumes are required.** A
     non-divergence stencil reads a ring's curvature as variation along the band
     and flattens φ (it failed the exact ring solution). Tests check the solver
     against ln(r/R) between circles, and against slanted straight bands.
3. **Distance across the bands.** φ is re-expressed as a distance s in pixels:
   the area between two levels divided by their length (the co-area formula).
   This is robust where φ steps at band edges.
4. **Bands.** The mean colour is profiled along s at 0.5 px. A band edge is a
   local maximum of the colour change above 2 × its 25th percentile, which is
   the noise level since most bins lie inside bands. Small stray pieces (under
   10% of a band's largest piece) go to the nearest kept band. Every band is a
   whole level-set band by construction.
5. **Deposition time.** t_dep is s normalised, so it is continuous and increases
   with the band number.

## Validation (28 synthetic photos, as in ADR 0011)

| | ADR 0011 (patches) | this ADR |
|---|---|---|
| Bands seen / true: fortification, botryoidal | 142 / 34, 331 / 36 | 39 / 34, 22 / 36 |
| Forms present confirmed | seam 1–2 of 4, others 0 | botryoidal 4 of 4, others 0 |
| False positives, six reliable forms | 0 | 0 |
| False positives, eye | 7 | 4 (all on botryoidal photos) |

On the eight owner photos, the bands now trace as whole rings and layers. One
slab's floor layers come out horizontal. Each photo takes 6–10 s.

The confirmed-form figures vary between runs of the method. An intermediate
version confirmed seam and fortification-waterline once each but not
botryoidal. Tests now guard the botryoidal detection and the
no-false-positive claim.

## Consequences

- Bands are now whole, but most strict criteria still fail on photos:
  - fortification: closed-bands about 0.7–0.8 against 0.9, and corner turn
    widths not measurable;
  - waterline: planar 0.01 against 0.005 (the lowest boundary follows the
    curved wall lining);
  - seam: its bands are about 2.5 px wide at the validation resolution;
  - quartz is still not detected.
- Eye stays unreliable: botryoidal lobes read as eyes.
- Fixed with this change: the seam central-suture criterion now ignores pixels
  without a deposition time. Before, a NaN made the section's mean empty. This
  is a bug fix, not a change to the metric, and simulations are unaffected (the
  seam preset still passes with the same values).
- Next steps, still in M10:
  - sharper corners (a corner-aware orientation field);
  - higher analysis resolution for thin bands;
  - quartz and inclusion detection.
