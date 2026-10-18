# 53. Stick agate in 3D, colour in every view, a wider Randomize

- Status: accepted (owner approved the list, 2026-10-18)
- Date: 2026-10-18
- Builds on: [ADR 0049](0049-stick-agate.md), [ADR 0050](0050-pigments-and-a-palette.md), [ADR 0051](0051-randomize-and-a-lighter-app.md)

## 1. Stick agate in 3D

Stick agate was the only form without a 3D version.

- **Sticks as solid pieces** (`agatesim.volume.sticks`): each stick is a rod
  from its site on the growth surface along its crystal axis, `length_mm`
  long and `length_mm / elongation` in radius (the 2D crystal's width), its
  sites and axes drawn as for the 3D quartz crystals from the fixed reference
  lattice. Later stages grow around the rods as around any other piece of the
  exact solid. Two simplifications of the 2D growth law keep the distance
  exact: the far end is rounded (a capsule) rather than pointed, and sticks
  that cross join rather than stopping each other.
- **Both tiers**: a `stick` stage in the 3D staged model and Mode `STICK` in
  the 3D growth model. Sticks end as quartz (each with its crystal id) or, with
  `fill = "hollow"`, as moulds that no later stage enters.
- **Speed**: a point compares only the sticks whose axis samples are nearest
  (exact against comparing every stick, a test of 20,000 points); a 512 px cut
  through the 120 mm vein takes 0.4 s (7.5 s comparing every stick).
- **Presets** `stick-3d` and `stick-mechanistic-3d`: the 2D presets' vein
  (`seam-slab`, 120 mm) and sticks, cut across the sheet.

**Results on cuts.** The 3D runs work (rods lined by H1, quartz with crystal
ids, open moulds when hollow: tests), but neither preset passes as stick agate
on a cut. On the configured cut, the straight-stick share is 0.39 (H1) and
0.67 (procedural) against 0.75, and the wrap test 0.59 and 0.55 against 0.7;
no offset of the cut passes. On 100 random cuts both pass 0%: straight
sticks 0%, enough sticks 22% and 18%, wrap 26% and 20%, fill 67% and 79%.

A flat cut shows a stick as a full bar only when it runs along the stick;
most sticks cross a cut at an angle and show as short stubs, and the bands
around a rod cut off its axis lie at uneven distances from the stub. The tests
were written for slices that contain the sticks (ADR 0049), so in 3D the form
passes few cuts, as tube agate's rings show only on cuts across the filaments
(13%). A narrower spread of axes (5°) makes the straight-stick test pass on
most cuts but not the wrap test (0.22–0.58 against 0.7). Changing a verified
form's tests needs the owner's approval and an ADR; none is proposed here.

## 2. Colour in every view

- **Shadow and iris views** read the pigment: each pigment has its own
  absorption per colour channel (`optics.PIGMENT_ABSORPTION`, effective
  values chosen so each looks like its slab colour), so reflected light
  through a hematite band comes back red, through celadonite green, and light
  through the iris slice is tinted by the band's pigment. With no pigment named
  the iron path is unchanged, so every shadow and iris test scores as before.
- **H2 (Liesegang)** takes a palette: each precipitate band draws one pigment,
  in 2D and 3D, at no extra cost on the GPU lattice.

## 3. A wider Randomize

Randomize may also vary, when asked ("Also vary" in the app):

- **cavity**: another preset shape of the same host (volcanic, sedimentary or
  seam), with probability equal to the strength; size within a factor of 1.3
  either way; any rotation. Left alone when tubes are placed.
- **timelines**: events shift by up to 10% of the run; the silica and iron
  levels vary within 0–1; on/off switches (settling, spherulites, dendrites,
  sticks) keep their values, so no stage switches on or off by accident.
- **stage order** (staged model): a random order from the allowed list.

Draws are still checked as before (mechanistic models, and "stay within the
form"). Tests in `tests/test_explore.py`.
