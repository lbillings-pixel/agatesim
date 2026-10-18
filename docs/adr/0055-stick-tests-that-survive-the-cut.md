# 55. Stick tests that survive the cut

- Status: accepted (owner approved, 2026-10-18)
- Date: 2026-10-18
- Amends: all four stick-agate criteria ([ADR 0049](0049-stick-agate.md))
- Builds on: [ADR 0024](0024-eye-and-geode-tests-on-cuts.md), [ADR 0053](0053-stick-agate-in-3d-colour-in-every-view-wider-randomize.md)

## Context

ADR 0053 found that 3D stick agate passes no random cut. The tests were
written for slices that contain the sticks (ADR 0049): they asked for patches
at least four times longer than wide, and for bands at an even distance all
round each one. A flat cut runs along a stick only by chance; most cross it at
an angle and show a short oval stub, and the bands around a rod cut off its
axis show as larger ovals of the same shape, so their distance from the stub
varies round it. As with the eye and geode tests (ADR 0024), the 3D form is
right and the tests assume the cut. The owner asked for tests that work on
angled cuts.

Two things hold on any cut through a rod of radius r, whatever the angle:

- **Its width.** In the cut plane, the direction across the rod's projected
  axis is not foreshortened, so every section of the rod, bar or stub, is 2r
  wide. Measured on 15 random cuts of `stick-mechanistic-3d`, 98–100% of
  patches are convex and the sections' widths spread by only 1–12% (quartile
  range over median) about 0.72 mm.
- **The bands beside its flanks.** A point in the plane at (s, t), across and
  along the section from where the axis meets it, lies √(s² + t² sin²φ) from
  the axis, φ being the angle between the axis and the plane. Near the middle
  of the section (t small) that is about |s|: beside the flanks, the bands
  keep their true distance from the rod at any angle.

## Decision

The four criteria, with their thresholds unchanged (owner approved):

| Test | Was | Now | Negative control |
|---|---|---|---|
| `stick-sections` (was `straight-sticks`) | ≥ 75% of sticks 4× longer than wide, filling ≥ 60% of their oriented box | ≥ 75% of sticks are sections of rods: filling ≥ 60% of their oriented box and within 25% of the median section width (√12 × the spread across) | moss (branched, no convex sections) |
| `stick-count` | ≥ 5 straight sticks | ≥ 5 stick sections | fortification (none); tube (2 filaments) |
| `pseudomorph-fill` | over the straight sticks | over the stick sections | the same sticks made opaque; tube (opaque filaments) |
| `bands-wrap-sticks` | the worst straight stick's share of nearby band boundary within 15% of its band's median distance | that share for band boundary beside the sections' flanks (within 30% of a section's half-length of its middle), pooled over the sections | the sticks pasted onto bands that never saw them |

A filament seen end-on looks like a stick cut across, so the tube control now
fails on the filling (opaque) and the count (two filaments), not on the shape.

**Resolution.** The wrap test needs a few pixels between a stick under a
millimetre wide and its first band. In the 120 mm vein that takes 768 px: the
presets' own resolution, at which CI verifies them, and now the least a survey
or the app's cut panel uses when judging stick agate
(`volume.survey.MIN_CUT_RESOLUTION`). At 384 px no band lies far enough
beside a stick to judge, and the wrap test fails; the stick negative controls
run at 768 px too.

## Results

- **2D presets** (768 px, CI): `stick` passes (sections 0.94, 45 of 48
  patches, width 0.83 mm; count 45; fill 1.0; wrap 0.98 over 14 sticks);
  `stick-mechanistic` passes (0.94; 44; 1.0; wrap 1.0 over 27 sticks). Hollow
  moulds still pass.
- **Negative controls** all fail their own test: moss has no convex sections;
  tube has 2 opaque sections (count 2, fill 0); fortification has none; the
  opaque sticks fail only the fill; the pasted sticks fail only the wrap.
- **Pasted control on 3D cuts:** on 20 random cuts of each 3D preset, the
  same sections pasted onto bands that never saw them score 0.18–0.46 on the
  wrap test (real: 0.87–1.0 where judged); none passes.
- **Random cuts** (100 each, 768 px, seed 0):

  | 3D preset | Old tests | New tests | stick-sections | stick-count | pseudomorph-fill | bands-wrap-sticks |
  |---|---|---|---|---|---|---|
  | stick-3d | 0% | 66% | 98% | 100% | 100% | 68% |
  | stick-mechanistic-3d | 0% | 74% | 99% | 100% | 100% | 75% |

  The wrap test sets the rate. An earlier sample of 20 cuts suggested 80–90%;
  the 100-cut figures stand. An oblique cut at 60° to the vein passes all four
  tests (a test).

## Consequences

- Stick agate stays verified at both tiers, on the new tests; its 3D presets
  now pass most random cuts.
- Cuts that run nearly parallel to the vein and through its stick layer show
  70–100 crowded sections with no banding between them; the wrap test has
  nothing to judge there and fails.
