# 49. Stick agate

- Status: accepted (owner approved the form, its tests and both tiers, 2026-10-17)
- Date: 2026-10-17
- Builds on: [ADR 0004](0004-archetype-ladder.md), [ADR 0035](0035-what-the-mechanistic-tier-requires.md), [ADR 0037](0037-mechanistic-quartz-geode.md), [ADR 0039](0039-mechanistic-eye-and-tube.md)

## Context

The owner asked for a thirteenth form, stick agate, if the literature gave
specific guidance. Stick agate shows straight, crystal-shaped rods inside the
agate, from Ankara (Turkey) and Morocco.

## Literature (thin, stated plainly)

- **The form.** Hatipoğlu and Dora studied the Ankara (Çubuk) agates
  [@hatipoglu2000], but the paper could not be read here (a Turkish scan).
  Search summaries of related listings by the same author, not read, describe
  andesite-hosted "barred agates": bar-shaped inclusions of chalcedony and
  quartz pseudomorphs, the bars older than the agate, some dissolved to leave
  hollow tubes. This is citation-level only.
- **The original mineral is not settled.** Dealers say aragonite; a
  mineral-database locality note, seen only in a search summary, suggests
  anhydrite. The model leaves it open: a blade-shaped crystal of some earlier
  mineral.
- **The process is better sourced.** In sedimentary rocks, agate formation is
  often accompanied by silica replacing pre-existing soluble minerals,
  sulfates and carbonates ([@goetze2020] §6). Quartz pseudomorphs after
  anhydrite are known from geodes ([@chowns1974], abstract).

## Decision

1. **The archetype** `stick` (rung 13, depends on tube agate: lining grown
   around solid objects). A stick is a connected patch of quartz, open space
   or inclusion inside the agate, other than the patch at the cavity's
   deepest point. Its four tests (owner approved), each with a negative
   control in `tests/test_criteria.py`:

   | Test | Measure | Pass | Negative control |
   |---|---|---|---|
   | straight-sticks | share of sticks ≥ 4× longer than wide and filling ≥ 60% of their oriented box | ≥ 0.75 | moss (branched) |
   | stick-count | straight sticks | ≥ 5 | fortification (none); tube (round) |
   | pseudomorph-fill | share of the straight sticks' area that is quartz or open | ≥ 0.9 | the same sticks made opaque |
   | bands-wrap-sticks | worst stick's share of nearby band boundary within 15% of its band's median distance from the stick | ≥ 0.7 | the sticks pasted onto bands that never saw them |

   "Nearby" means at most half as far from the stick as from any other
   solid, since sticks start on the wall.
2. **The sticks' growth** (`grow_sticks` in `agatesim.models.growth`):
   crystals nucleate on the growth surface (blue-noise sites on the exact
   wall) and grow with a blade habit, the tip at full rate and the sides at
   1/elongation, competing by geometric selection: the quartz crystals'
   growth law (ADR 0037), run for a set tip growth. Each stick is a prism
   that long and about 2 × length / elongation wide, with a pointed tip,
   unless a neighbour got there first. Parameters, all `effective`: spacing,
   length, elongation (the habit), axis scatter; and what replaces them.
3. **Procedural tier:** a `sticks` schedule in the growth model (Mode
   `STICK`), with its parameters; the bands are procedural as usual. Preset
   `stick`.
4. **Mechanistic tier:** a `stick` stage in the staged model (order
   `stick-wall`), then H1 lines the sticks and the wall. Preset
   `stick-mechanistic`. The stage order, how long the crystals grow before
   the silica arrives, and the replacement are scheduled changes of
   conditions (ADR 0035 rule 2); the sticks' shape comes from the growth law
   and the bands from H1.
5. **Replacement:** at the end the crystals become quartz (a pseudomorph,
   each keeping its crystal id) or dissolve and leave hollow moulds
   (`fill = "hollow"`).
6. Not in 3D yet (rejected with a message).

## Results

- `stick` passes at 768, 384 and 256 px: 13 straight sticks, straight share
  0.87, pseudomorph fill 1.0, wrap 0.76, 0.77 and 0.82.
- `stick-mechanistic` passes at 768, 384 and 256 px: 15 straight sticks of
  17 patches (0.88), fill 1.0, wrap 1.0. With hollow moulds it passes too.
- The procedural wrap is lower because its bands wobble by 0.1 mm, a large
  share of the distance for the bands nearest a stick; H1's bands don't.
- The patches that fail as straight are two or three sticks that cross and
  merge; real stick agates show crossings too. Wider spacing (6 mm) and a
  narrower spread of axes (25°) keep the presets clear of the threshold.
- Sticks ignore the grid: a 256 px run's stick pixels fall on a 512 px run's
  sticks (more than 85%).

## Consequences

- Thirteen forms, each verified at both tiers.
- Stick agate's mechanistic verification rests on thin sourcing for the
  form itself; the ADR names it as such. Reading the Hatipoğlu and Dora
  paper would test the picture (and might settle the original mineral).

## Amendment (2026-10-17): the paper read; the presets in a vein

With a PDF library and OCR (owner approved), [@hatipoglu2000] was read in
full (OCR of the Turkish scan, imperfect in places). It confirms the form and
changes two details:

- **The form, confirmed.** Agates in the Ankara andesites contain
  "completely silicified" stick-like structures of rectangular-prism shape,
  with fine striations along the prism, that keep the original crystal shape
  (pseudomorphs). Seen first and only there, they were named stick agate
  ("Çubuklu Agat"). Trace-element analyses of the sticks find Fe, Pb and Zn.
- **The original mineral: probably a zeolite.** In a contact-zone fracture
  the sequence from wall to centre is tremolite, chlorite, silicified
  radiating pseudomorphs ("probably zeolite"), then agate banding. Not
  anhydrite or aragonite, as dealers and a database note had it. The model's
  crystals stay generic; zeolites grow as prisms and radiating sprays, which
  the blade habit already gives.
- **The setting: veins.** The stick-bearing agates fill crevice and fissure
  veins in andesite (1 mm to 10 cm wide), with concentric bands and no
  horizontal ones; the nodular, vesicle-filling agates are in the rhyolite.

So both presets now use a crevice vein (`seam-straight`, 120 mm long, about
12 mm wide), with sticks scaled to it (spacing 4.5 mm, length 5 mm,
elongation 12, about 0.8 mm wide); the registry lists the form's hosts as
volcanic and seam. Earlier the same day the presets had moved from a
sedimentary nodule to a volcanic vesicle; the vein is closer to the paper.

Results at 768 px: `stick` 45 straight sticks of 48 (0.94), fill 1.0, wrap
0.83; `stick-mechanistic` 44 of 47 (0.94), fill 1.0, wrap 1.0. Both pass at
384 px too. At 256 px a pixel is 0.47 mm across the 120 mm seam, too coarse
to resolve bands beside sticks under a millimetre wide, so the wrap test
fails there; CI verifies at 768 px.
