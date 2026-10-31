# 76. Changes for Nodule's first slice: capped wobble, fold check, and what follows

- Status: accepted in part (2026-10-31): sections 1–2 done; 3–5 planned
- Date: 2026-10-31
- Builds on: [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (formation work moves to Nodule)
- Spec: Nodule's ADR 0005 (`docs/adr/0005-representation-implicit-hybrid.md`,
  sections 2–5), which gives the sources; its reading notes are in Nodule's
  `notes/n2-reading/`

## Context

Nodule's vertical slice reads agatesim's growth model as a band coordinate:
growth time t(x), starting from wall distance d plus a wobble. Nodule needs
five things from agatesim, each made here with tests: (1) a wobble whose slope
is capped below 1 mm per mm, with a check that bands don't fold; (2) a
Lipschitz bound per `Solid`, for sphere tracing; (3) fracture events;
(4) band-limited noise; (5) a wall-distance cache, only if slice cuts are slow.

## Decision

### 1. Capped wobble and the fold check (done)

**What was there.** The 2D and 3D fortification and growth models add
wobble · n(x) · min(d / 2·wobble, 1) to d, where n is unit-variance noise read
from a lattice by linear interpolation. The taper alone has slope |n|/2, which
passes 1 wherever |n| > 2. Measured on the ten 3D presets that use the taper
(1,400–1,900 random points within about 0.3 mm of the wall each): the
coordinate runs backward at 0.7–3.5% of them. The noise's own slope stays at or below 0.26 mm/mm. Almost all of those points have
a coordinate ≤ 0, which clamps to the first band, so the folds rarely show:
uncapped fortification-3d gave 1 fold in 5,823 sampled pairs, as deposition
time (below).

**The cap.** New parameter `wobble_max_slope` (effective, mm/mm, 0 ≤ s < 1)
on `ProceduralFortification` and `ProceduralGrowth`, in 2D and 3D (owner's
choice). It is opt-in: 0, the default, keeps the old taper, and all 29 2D
presets and 7 checked 3D presets give bit-identical results. With s > 0:

- the noise lattice gives exact bounds (`models.base.lattice_bounds`): peak
  |n| ≤ max |lattice| (interpolation stays within the lattice's range), and
  |∇n| ≤ √(Σ_axes (max edge difference / spacing)²) (within a cell each
  gradient component is a weighted mean of that axis's edge differences);
- the taper width becomes D = wobble · peak / (s − wobble · slope), so the
  whole added term, taper included, has slope ≤ wobble · (slope + peak / D) = s;
- if the noise alone is at least as steep as s, the run is refused with a
  message (lower `wobble_mm` or raise `wobble_scale_mm`).

Below 1, d + added term increases inward wherever |∇d| = 1, so bands cannot
fold away from the medial surface (mathematics). The price: the wobble fades
in over D instead of 2·wobble. Defaults (0.1 mm at a 2 mm scale, cap 0.5) give
D ≈ 1.8 mm; fortification-3d (0.12 mm) about 2.7 mm. Thickness of a band stays
within 1/(1 + s) to 1/(1 − s) of its mean.

**Where the guarantee holds.** Wall-lining coordinates: fortification without
corner rounding, and growth's lining stage. It does not cover 2D corner
rounding (blurred distance has |∇d| < 1 at corners), growth's spherulitic
stage (its metric distance scales with each site's rate), bands lining tubes
or following crystals, or settled bands (level, not lining). The check below
reports folds in those, as expected.

**The check** (`agatesim.folds`) reads only Fields (deposition time `t_dep`)
and geometry (wall distance): `fold_check_points` steps points 0.1 mm along
∇d (longer than one growth time step, ≈0.075 mm) and compares t_dep there and
back; `fold_check_grid` does the same with central differences on a 2D or 3D
grid. Both skip the medial surface (d grows by less than 0.9 of the step, or
|∇d| strays from 1). Results (`tests/test_folds.py`):

| Run | Checked | Folds |
|---|---|---|
| fortification-3d, cap 0.5 | 5,748 | 0 |
| tube-3d without filaments, cap 0.5 | 10,491 | 0 |
| 2D fortification / tube without tubes, cap 0.5 | 58,043 / 71,798 | 0 / 0 |
| negative control: wobble 3 mm, no cap (same four) | | 475 / 740 / 9,233 / 6,747 |

A cap also refuses that steep wobble outright. Cost: bounds take one pass over
the noise lattice (milliseconds); the 3D check takes 0.2–0.3 s for 20,000
points.

### 2. Lipschitz bound per Solid (done)

Sphere tracing marches a ray by the value of `level` (signed, positive
inside) divided by a bound on its slope, so it never steps across the wall.
Every `Solid` now reports `level_bound()`: a `LevelBound(lipschitz,
error_mm)` meaning |level(p) − level(q)| ≤ lipschitz·|p − q| + 2·error_mm. A
ray may then step (|level| − error_mm) / lipschitz. The method is abstract, so
a new solid must state its own.

| Solid | lipschitz | error_mm | Why |
|---|---|---|---|
| Ellipsoid | 1 | 0 | level = a_min(1 − \|p/a\|); \|p/a²\| ≤ \|p/a\| / a_min |
| Polyhedron | 1 | 0 | the least of plane distances |
| SphereUnion | 1 | 0 | the greatest of r − \|p − c\| |
| Prism, drawn shapes | 1 | extent / 8000 | outline sampled at most extent/4000 apart |
| Revolution | 1 | extent / 8000 | as Prism; (x, y, z) → (x, √(y² + z²)) moves no point pair farther apart |
| Rotated | inner's | inner's | a rotation keeps distances |

For a 50 mm stone the outline error is about 6 µm, below any useful tracing
tolerance. Fractures narrower than the tolerance would vanish, so Nodule
checks its fracture field separately (its ADR 0005). Tests
(`tests/test_level_bound.py`): every preset solid, turned, and a drawn one,
over 40,000 point pairs from 1 µm to the whole solid apart, inside and out;
negative control: a level 1.5× steeper than its reported bound is caught.
Cost: none at run time (constants).

### 3. Fracture events (planned)

### 4. Band-limited noise (planned)

### 5. Wall-distance cache (only if Nodule's slice cuts are slow)

## Consequences

- Nodule turns the cap on (its ADR 0005 suggests s = 0.5) and can run the
  fold check on its own composite.
- Existing presets, the gallery and verified archetypes are unchanged.
- The new parameter appears in the app automatically (from the schema).
