# 21. Three-dimensional runs, judged on cuts

- Status: accepted
- Date: 2026-10-16
- Builds on: [ADR 0003](0003-model-architecture.md), [ADR 0013](0013-mechanistic-front-feedback.md), [ADR 0016](0016-mechanistic-settling.md), [ADR 0020](0020-staged-mechanisms.md)

## Context

Every result so far was a 2D cross-section. Real agates are 3D bodies, seen
through whatever cut the saw made. Some questions need the third dimension:

- how often a random cut through a nodule shows its form;
- how much thicker bands look on an oblique cut than they are;
- whether gravity can be recovered from cuts that don't contain it.

The literature pass for M9 found no 3D (CT) study of agate banding. The one
useful new source was Moxon et al. [@moxon2013], on the timing of the combined
form's stages (ADR 0020). M9 therefore rests on the models, not on 3D data.

## Decision

1. **A separate 3D path** (`agatesim.volume`). The 2D code is unchanged in
   behaviour: the shared H1 and H4 numerics were refactored so they take wall
   distances or heights as arrays, and every 2D preset gives bit-identical
   fields before and after.
2. **Cavities are solids**, not voxel masks. Each answers *is this point
   inside*, *how far is the wall* and *how far does the solid reach in a
   direction*. Presets: ellipsoidal vesicle and nodule, a spindle-shaped
   (almond) vesicle revolved from the 2D almond outline, a flat-faced
   polyhedral nodule, lobed and lumpy nodules as overlapping spheres, and
   sheet-like seams extruded from the 2D seam outlines. A drawn outline is
   extruded. Wall distances are exact, except near the seams between
   overlapping spheres, where they come from wall samples about 1/400 of the
   cavity apart.
3. **Models are evaluated at points.** The models brought to 3D are procedural
   fortification and waterline, H1, H4 and the H1 + H4 stages. They all set a
   point's fields from its wall distance, its height, or both, plus a history
   computed once for the cavity. So a model is prepared once, then evaluated
   at voxel centres for a volume, or at the pixels of a cut at any resolution.
   In the staged model, the distance to the nearest solid at a later stage is
   exactly min(wall distance − rim depth, height − bed top).
4. **Whole-cavity quantities come from a fixed lattice** of 128 points along
   the longest side, the same at every resolution. These are the deepest
   point, H1's filled volume share against depth, and H4's cross-section area
   against height. H4 needs no new physics in 3D: its column's widths become
   cross-section areas.
5. **Cuts are 2D results.** A cut's outline is the cavity's cross-section,
   exact for flat-faced solids and traced finely from the solid otherwise. Its
   wall distances are in-plane, its fields are the 3D model evaluated at its
   pixels, and gravity is projected onto it. The renderer, criteria,
   statistics and optics then read a cut as they read a photo of a slab. No 2D
   criterion was changed.
6. **Random-cut surveys.** A survey judges cuts with normals uniform over the
   sphere, offset within 60% of the cavity's half-extent. It also compares the
   bands' apparent thickness on each cut with their true thickness, measured
   along the 3D wall normal. Both are the median thickness of the first five
   bands from the wall.
7. **Viewer.** A 3D screen holds a WebGL2 ray-marched view of the volume's
   colours, opened at the cut and rotatable, next to the cut rendered as a
   slab. It has sliders for the cut and a survey button. It is written in plain
   WebGL2, so the web app gained no dependency.

## Results

All six 3D presets were surveyed with 100 random cuts each (seed 0). The cuts
were 768 px for fortification and 512 px for the rest. "Gravity in the cut" is
the share of gravity that lies in the cut's plane: 1 means a vertical cut
through an upright nodule.

| 3D preset | Cuts passing | Failing criterion | By gravity in the cut (<0.5 / 0.5–0.9 / ≥0.9) |
|---|---|---|---|
| fortification-3d (procedural, angular nodule) | 30% | corners-preserved (all failures) | — |
| fortification-mechanistic-3d (H1) | 24% | corners-preserved (all failures) | — |
| seam-mechanistic-3d (H1, sheet) | 65% | elongate-host 66%, mirror and suture ~85% | 92% / 73% / 49% |
| waterline-3d (procedural) | 95% | — | 62% / 100% / 100% |
| waterline-mechanistic-3d (H4) | 93% | — | 46% / 100% / 100% |
| fortification-waterline-mechanistic-3d (H1 + H4) | 92% | two-domains | 54% / 95% / 100% |

- **Fortification corners don't survive most cuts.** Wall-parallel (98%),
  closed-band (≥99%) and band-count (100%) tests pass almost every cut.
  The corner test fails most of them, for a geometric reason. On a cut, each
  face's bands advance at their own apparent rate (1/sin of the angle between
  face and cut), so a band's corner drifts off the wall corner's bisector.
  Faces lying outside the plane also add corners that the wall doesn't have.
  The bands stay perfectly sharp (they are sections of offset polyhedra). The
  2D criterion assumes the corner lies on the bisector, so it doesn't find it
  (in 17–31% of cuts the turn isn't found at all; 8–9% can't be judged). That
  assumption is exact in 2D and wrong for oblique cuts. As a result, the
  criterion would reject many real fortification agates on an ordinary cut
  face.
- **Horizontal layers survive almost every cut** that contains a fair share of
  gravity. They fail mainly when gravity is nearly normal to the cut, where the
  layers become broad patches. Gravity is recovered from the cut (geopetal
  test) in 94–96% of cuts.
- **Seams** fail mostly on cuts that run along the sheet. Those show a broad,
  not an elongate, section.
- **Apparent band thickness.** For random cut angles, geometry predicts a
  median stretch of 1/sin 60° = 1.155. The procedural fortification gives a
  median of 1.18 (quartiles 1.05–1.30), H1 1.07 (1.02–1.17) and the seam 1.18.
  A tilted cut through even bands in a flat sheet gives 1/cos θ, within a
  pixel (a test).

## Consequences

- 3D runs are records like 2D ones (`agatesim volume run`), with the volume's
  fields, the configured cut, its criteria and an optional survey. The 2D run
  browser ignores them.
- Growth from nuclei (botryoidal, eye), dendrites, quartz crystals, tubes and
  H2 aren't in 3D yet. H2 in 3D needs the GPU solver.
- Changing the corner criterion so that it follows each band's own corner
  would need its own ADR, because the criterion is verified.
