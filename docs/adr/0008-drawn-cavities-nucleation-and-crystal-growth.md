# 8. Drawn cavities, nucleation and crystal growth

- Status: accepted
- Date: 2026-10-15

## Context

M4 adds three forms that grow from points rather than from whole surfaces:
botryoidal and eye agate (spherulites nucleated on the growth surface) and tube
agate (banding around filaments that cross the cavity). The owner also asked for
a drawing tool for cavity shapes, offering both corner clicking and freehand
sketching with an angular/smooth choice. They also asked for the M3 quartz
simplification to be fixed now: equant crystal cells and a smooth open centre.

## Decision

1. **Drawn cavities.** A cavity is either a preset or a drawn outline with a host
   setting. Only the outline's shape is used; `size_mm` and `rotation_deg` place
   it like a preset. An outline must have at least 3 distinct points and no
   self-intersections. "Smooth" applies Chaikin corner cutting (4 rounds) on the
   backend, so runs are reproducible from the stored control polygon. The UI
   checks outlines with a TypeScript port pinned to a shared fixture
   (`tests/fixtures/outlines.json`).
2. **Tubes** are part of the cavity's geometry: filaments seen end-on, given as
   positions (mm from the cavity centre) and radii. They become a new
   `INCLUSION` phase, which M5 will reuse for dendrites. They are growth
   surfaces from the start, like the wall. Tubes must lie wholly inside the
   cavity.
3. **Growth modes.** The growth model gains a scheduled `spherulitic` condition.
   Each time step has one mode, with precedence settling > crystal (quartz) >
   spherulitic > lining. Every non-settling stage is solved as the earliest time
   at which growth from the stage's starting surface reaches each pixel:
   - *lining:* distance from the solid;
   - *spherulitic:* distance from the nearest nucleation site divided by that
     site's growth rate (log-normal spread);
   - *crystal:* each quartz crystal has a pointed, prism-shaped growth form with
     its long axis scattered about the surface normal.
4. **Nucleation sites** are placed with blue noise on the stage's starting
   surface. Candidates are drawn uniformly in world coordinates; those near the
   surface are projected onto it and accepted in draw order with a minimum
   separation. All draws are made before any filtering, so sites don't depend on
   grid resolution. On the first stage the surface is the exact wall and tube
   geometry; on later stages it is the pixel boundary of the open space.
5. **Quartz coarsening is no longer imposed.** It emerges from geometric
   selection [@vanderdrift1967]: crystals aimed along the growth direction
   outgrow their neighbours. `quartz_coarsening` is retired; `quartz_elongation`
   and `quartz_axis_scatter_deg` replace it. Old run records that carry it still
   load (the value is ignored).
6. **Criteria for radial growth** read only Fields and geometry. The curvature of
   the deposition-time isochrons shows whether growth radiates from a point
   (diverging, convex in the growth direction) or converges like lining in a
   convex cavity. Each diverging pixel's centre of curvature votes for where
   growth came from, and peaks in the vote density are growth centres.
   - **botryoidal:** `lobate-front` (at least 0.6 of the surface next to the open
     space diverging), `lobe-count` (at least 5 separate bulging stretches) and
     `bands-follow-lobes` (at least 0.7 of band boundaries diverging).
   - **eye:** `discrete-eyes` (at least 3 growth centres), `wall-nucleated` (at
     least 0.8 of them on the wall) and `isolated-eyes` (at least 0.3 of the
     first banding on the wall is ordinary layering).
   - **tube:** for each seed, `seed-concentric` (at least 0.8 of band boundary
     within 10% of its band's distance from the seed) and `seed-placement` (fitted
     ring centres within 0.1 of the ring zone's radius).

   These replace provisional criteria that had no thresholds. The old botryoidal
   criterion "lobe radius decreases as nucleation density increases" is a
   comparison between runs, so it becomes a test. That test is restricted to thin
   crusts: in the model, as in Huygens' construction, a crust much thicker than
   the site spacing grows towards a smooth layer unless rates differ, and then
   lobe size is set by competition, not by nucleation density.

## Consequences

- The UI gains a drawing dialog (click corners or freehand; angular or smooth;
  host), a "Your own" cavity entry, and tube placement by clicking the live
  preview. Preview responses now carry the grid origin.
- Shape changes clear tubes, since they may not fit the new shape.
- Simplifications to revisit:
  - Growth reaches pixels in straight lines, so in strongly concave cavities
    growth can cross a thin spur of solid. A geodesic (fast-marching) solver
    would fix this.
  - Eye agate is judged in cross-section (half-ring systems on the wall). Eyes
    seen as circles on a surface ground parallel to the wall need the 3D model
    (M9).
  - Tubes are straight filaments perpendicular to the slab; oblique or curved
    tubes also need 3D.
  - Isochron curvature uses deposition time. Photo analysis (M7) has no
    deposition time, so it will need an ordering estimated from band nesting.
