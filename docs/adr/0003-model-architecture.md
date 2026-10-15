# 3. Model architecture: 2D first, procedural first, mechanisms pluggable

- Status: accepted
- Date: 2026-10-14

## Context

- **There is no consensus on how agate bands form** ([@goetze2020], [@moxon2020]).
  Competing ideas include self-organization in a silica gel or at the growth front
  ([@wang1990], [@heaney1995]), Liesegang-type precipitation–diffusion
  ([@krug1994]), repeated pulses of incoming fluid, and gravity settling of
  particles ([@lu1994]).
- **The scales span orders of magnitude.** Nodules are centimetres to decimetres
  across. Bands can be micrometres thick, and the crystallites making up the
  fibres are only 8–100 nm long ([@lu1994]). Fully resolving that in 3D is not
  feasible.
- **Some archetypes are optical.** Shadow and iris agate are about how light passes
  through finished banding, not how it forms.
- **The owner wants convincing results early and physics later.**

## Decision

1. **2D cross-sections first.** Agate is studied and admired as cut slabs. The core
   uses dimension-agnostic interfaces so 3D can be added later.
2. **Two layers of formation model behind one interface:**
   - *Procedural models* are fast and controllable. They produce plausible
     structure from geometric rules, such as offsetting the wall and modulating
     band properties.
   - *Mechanistic models* evolve physical fields (silica concentration,
     precipitate, phase, impurities) with reaction–diffusion, phase-field or
     settling dynamics.

   Both produce the same output fields, so the archetype criteria, the renderer
   and the UI treat them alike.
3. **Mechanisms are swappable components**, not hard-wired. A run's config names
   which mechanisms are active, so one question can be put to the simulator:
   *which mechanism and conditions reproduce form X?*
4. **Formation and optics are separate subsystems.** Formation outputs material
   fields: phase, impurity content, fibre orientation, porosity. A separate
   renderer turns them into appearance (colour, translucency, and later wave
   effects for iris agate).
5. **Conditions are schedules, not constants.** Every environmental variable can
   vary over model time (steps, ramps, pulses), because many agates record a
   sequence of conditions.
6. **Every parameter is labelled** as `physical` (a measurable quantity with
   units) or `effective` (a model coefficient with no direct measurement). The UI
   shows the label.

## Consequences

- Procedural results can be shown early. Replacing them with mechanistic ones
  doesn't change the UI or the tests.
- Multiple mechanisms mean more code, but enable comparisons between them that
  are scientifically useful.
- Results must not be presented as evidence for a mechanism when they come from
  procedural models.
