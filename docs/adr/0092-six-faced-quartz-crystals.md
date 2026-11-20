# 92. Six-faced quartz crystals (3D)

- Status: accepted (owner, 2026-11-19, from Nodule: "six-faced crystal tips in agatesim",
  approved as Nodule's work plan item 19 records; the form and parameter below are
  Claude's choice within that). Built 2026-11-20 on branch `six-faced-tips`, not yet
  pushed (pushing and moving Nodule's pin wait for the owner).
- Date: 2026-11-20
- Builds on: [ADR 0023](0023-growth-from-nuclei-in-3d.md) (crystals in 3D),
  [ADR 0090](0090-the-crystal-wall-for-rendering.md) (the crystal wall and its closed form)
- Spec: Nodule's ADR 0019 s.6.12 ("Diagnosis": the hollow's crystal wall read as uniform
  fur; the crystals' round tips are the first suspect)

## Context

A 3D crystal stage grows each crystal as a cone on a cylinder (`Crystals.pair_times`):
round across its axis. Real quartz is a six-sided prism under a six-sided pyramid of
rhombohedral faces, the faces of the pyramid sitting over the prism's. Cut faces and
2D cross-sections hardly show the difference, but Nodule now renders the hollow a geode's
crystals leave as air (ADR 0090), where light reflects off the crystal tips: round cones
mirror light as soft streaks, and the owner read the wall as "fur". Flat faces should
read as facets and glint under a small lamp.

## Decision

- **The form.** `Crystals(..., faces)`: with `faces` n >= 3, the distance across the
  axis is measured to the nearest of n face planes through the axis's offset, i.e. the
  offset's part across the axis projected on the nearest of n face normals (at whole
  multiples of 360/n degrees from the crystal's first face normal). It replaces |q| in
  both terms: tip = |along| + across cot(alpha), side = across x elongation. So the
  prism has n flat sides advancing at the side rate, and the pyramid n flat faces leaning
  at the tip half-angle (38 deg, ADR 0023) to the axis, each over a prism face, as in
  quartz. The section is the regular n-gon whose inscribed circle is the round form's:
  across lies between |q| cos(180/n) and |q|, so a faced crystal reaches every point no
  later than the round one would (it contains the round form; six faces add ~10 % to
  the section).
- **Its turn.** Each crystal's first face normal turns about the axis by 360/n x the
  site's first uniform draw (`_Sites.draws[:, 0]`), which crystal sites never read before
  (it is the spherulites' rate draw). No stream is added or shifted, so sites, axes and
  every other draw stay as they were; the frame is built from the axis alone.
  Resolution-independent like the sites.
- **The parameter.** `quartz_tip_faces` (growth model, 3D runs only; `physical`: 6 for
  quartz), default 0 = the round form, bit for bit (tested), so agatesim's presets and
  archetypes do not move. The FrontFeedback model's crystals stay round.
- **The closed form (ADR 0090 extended).** `CrystalWall.packed()` rows are 9 numbers:
  site, axis, first face normal (zeros when round); `ROW` and the CUDA source's
  `AGATESIM_CRYSTAL_ROW` say so. `shape_numbers` returns (cot_alpha, elongation, faces)
  and the device functions take `int faces`. The CPU chooses the face by the nearest
  multiple of the sector to atan2 of the offset's two components; the device steps round
  the face normals instead (cos and sin of k sector by rotation, exact constants for six
  faces) and keeps the one the offset projects on most, which is the same face up to
  ties, where the projections are equal, and takes no atan2, sin or cos per crystal.
  Across is the projection itself, so float32 keeps ADR 0090's accuracy.
  The gradient's across part is the chosen face normal. A breaking change for callers of
  the device functions (Nodule), made with them.

## Tests (tests/test_crystal_wall.py)

- Round crystals: `pair_times` equals the earlier formula exactly; no face normals.
- Six faces: across equals |q| along each face normal and |q| cos 30 deg at each corner,
  lies between the two elsewhere; face normals are unit and across the axis; a rebuild
  gives the same values. Control: the round form differs on most points.
- Faces 1, 2 and negative are refused.
- Device vs `pair_times` (float and double, near, far, on the axis, on the tip-side
  edge, and within 1e-4 rad of the planes between faces) and its gradient vs finite
  differences at smooth points. Controls: faces turned by 30 deg, or the device told the
  crystals are round, mismatch off the face normals.
- The quartz-geode-3d preset with six faces: the same sites and axes as round; its
  wall is positive exactly in its hollow (control: the round wall is not); it packs for
  the device and matches its arrival.

## Consequences

- On quartz-geode-3d (400k samples): the hollow is 2.93 % of the solid with six faces
  against 2.97 % round, quartz 13.65 % against 13.62 %; prepare 5.5 s against 5.4 s.
- Nodule reads the row stride and the face count from here; until its pin moves it
  keeps working with ADR 0090's six-number rows (its own shim).
- The 2D models are unchanged; whether agatesim's own presets should take six faces is
  left for the owner (it would move their cuts slightly).
