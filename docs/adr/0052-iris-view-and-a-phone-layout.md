# 52. The iris view, Undo beside Randomize, and a phone layout

- Status: accepted
- Date: 2026-10-18
- Follows: [ADR 0010](0010-optical-renderer.md), [ADR 0051](0051-randomize-and-a-lighter-app.md)

## Context

The owner tried the app on a phone and reported two things: Undo was too far
from Randomize (at the top of the page, above a long settings column), and
the iris view showed no colours at the default settings, nor any change with
the angle.

The iris view was dark for three reasons, measured on the presets:

1. It looked through the slab's full thickness (3 mm by default), where
   scattering hides the gratings; iris colours show only in thin, backlit
   slices (the iris presets use 0.3 mm). The botryoidal preset, with
   gratings in 23% of its pixels, showed no colour at any angle.
2. The default form's model (procedural fortification), and procedural
   waterline, had no regular micro-banding at all, so nothing diffracted.
3. The view tilted only sideways. Grating lines along horizontal layers
   diffract up and down, so waterline showed nothing at any angle.

## Decision

1. **A thin slice for the backlit view.** `OpticsConfig.slice_mm` (0.3 mm)
   is the thickness the iris view looks through, whatever the slab's
   thickness (which the shadow view still uses). The iris presets already
   used 0.3 mm, so their tests are unchanged.
2. **Micro-banding in the procedural fortification and waterline models**
   (2D and 3D): the growth model's `iris_fraction` (0.3 of the bands),
   `micro_band_um` (2 µm) and `micro_band_variability`, all `imposed`, drawn
   by one shared function (`base.micro_band_spacing`) from a new random
   stream. Regular micro-banding is reported in nearly every agate, often
   hidden by pigment ([@cartwright2026], as for the growth model).
3. **A direction for the iris view**: the app sends the tilt's direction in
   the slab plane (the server already took it), starting at 45° so layers of
   any orientation show colours. Where a result has no micro-banding (H1
   without its fast rhythm, H2, H4) the view says so and how to get it.
4. **Undo and Redo sit with Randomize**, in one row at the top of the
   settings column that stays in view while the settings scroll (desktop and
   phone).
5. **On a phone** the page scrolls as a whole, and the sticky row carries a
   small thumbnail of the live preview, so a change shows without scrolling
   to the slab.

## Results

- Iris colours at 30°, direction 45°: fortification 15% of agate pixels
  (was 0), waterline 20% (was 0), botryoidal 9% (was 0), the iris preset
  21–30% depending on angle; at 5° none, as the first orders are still in
  the ultraviolet. The pattern changes with the angle (a test).
- Only fortification, seam and waterline change, and only in their
  micro-band spacing; the 24 other 2D presets hash bit-identical, the
  growth model included (its draws moved into the shared function intact).
- Checked in a 400 px frame: settings first, the row sticks at the top,
  the thumbnail shows, no sideways scrolling; at desktop width the row sticks
  within the settings column and the thumbnail is hidden.
- Tests: `tests/test_iris_view.py`.
