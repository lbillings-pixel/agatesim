# 41. Reading for shadow, iris and plume agate

- Status: accepted (a record of reading; the criterion change proposed in §2 was approved and made in [ADR 0042](0042-iris-spacing-from-measured-gratings.md))
- Date: 2026-10-17
- Follows: [ADR 0035](0035-what-the-mechanistic-tier-requires.md)

## Context

ADR 0035 left shadow, iris and plume agate pending at the mechanistic tier,
each needing sourced physics. This records a time-boxed reading pass and what
it means for each form.

## 1. Shadow agate: what makes a band milky

- Milky and translucent chalcedony bands differ in water and density: from
  translucent grey to milky white, total water content and surface area fall
  and density rises; water sits at pore surfaces and at inner surfaces and
  defect regions ([@graetsch1985], abstract only).
- Iris bands, in contrast, occur only in pure, colourless chalcedony with little
  porosity ([@jones1952]).
- **For the model:** H1 varies the impurity incorporated and the growth speed.
  A mechanistic shadow agate needs a sourced link from those to water content
  or porosity, such as fast growth trapping more defects and water. No source
  read so far makes that link, so shadow stays pending. The H1 contrast test
  (0.43 against 0.6, ADR 0035) is not revisited until it does.

## 2. Iris agate: the grating

From the full text of [@jones1952] (pp. 578–584):

- The grating's lines are the edges of thin lamellae of alternately higher and
  lower refractive index, always at right angles to the chalcedony fibres, and
  continuous across neighbouring groups of crystals.
- **Spacing:** from about 15,000 down to 400 lines per inch, that is about
  1.7–64 µm; the figured specimen has about 10,000 (2.5 µm). Coarser gratings
  still diffract, with colours close to the beam.
- The thin layers have the higher index and are more quartz-like, not richer
  in opal.
- In the author's opinion the lines formed while the crystals grew, by rhythmic
  crystallisation at the front (compared with rhythmically banded organic
  melts), but not in the manner of the ordinary bands.
- **For the model:** a rhythm at the growth front with a period of micrometres
  to tens of micrometres, nested inside H1's visible bands, is a candidate
  consistent with Jones. It would be a second, fast oscillator (or H1 run with
  a micrometre boundary layer) in clear, impurity-poor bands only. Not built.
- **A mismatch in a verified criterion.** `grating-spacing` asks for a median
  micro-band spacing of 0.5–5 µm. That range comes from the review's
  defect-zoning scale ([@cartwright2026]), not from measured iris gratings.
  Jones measured iris gratings up to about 64 µm. **Proposal:** widen the range
  to 1–65 µm, sourced to Jones. Changing a verified criterion needs the owner's
  approval and its own ADR (ADR 0004), so nothing is changed yet. The
  procedural iris preset (2 µm) passes either way.

## 3. Plume agate: chemical gardens

- Chemical-garden growth is a reaction–advection process: a membrane forms
  around a dissolving seed, osmosis swells it until it bursts, osmotic and
  buoyancy forces expel the inner solution, and precipitation where it meets
  the outer solution builds the tube ([@cartwright2026] §4.3). Plume agate is
  interpreted as such a silica garden ([@goetze2020] §5.5).
- No quantitative model of plume growth in agate was found, and the review's
  section gives no model of chemical-garden growth either.
- **For the model:** buoyancy carrying fresh reactant from a branch's inside to
  its tip would make tips grow upward, a sourced process that the procedural
  upward stand-in only mimics. A mechanistic plume would release buoyant
  reactant from the aggregate and let it drift upward and precipitate where it
  meets the cavity fluid. Not built; it needs more reading on chemical-garden
  growth models first.

## Consequences

- Shadow, iris and plume stay pending at the mechanistic tier.
- Next steps, in order of readiness: (1) the iris spacing range (done, ADR
  0042); (2) iris by a micrometre-scale H1 rhythm in clear bands;
  (3) a chemical-garden growth model for plume, after reading on such models;
  (4) a source linking growth rate to water content, for shadow.

## Amendment (2026-10-17): growth rate and milkiness

A second, time-boxed search for a source linking a band's growth rate to its
milkiness (next step 4) found none that does so directly. Two partial links:

- Banding reflects differences in crystallite size, porosity, silica phase and
  pigments, and the high concentrations of lattice defects (silanol groups
  among them) point to rapid crystallisation ([@goetze2020], abstract).
- Milky bands hold less water than translucent ones and are denser
  ([@graetsch1985], abstract).

Chained, they would suggest that fast-grown, defect-rich bands are the wetter,
more translucent ones: the opposite of H1's current rendering assumption, which
makes its fast, impurity-rich bands milky (ADR 0013). The chain rests on two
abstracts and an inference, so nothing is changed. Shadow stays pending. Reversing H1's milky/clear assumption would
change how every H1 result looks, so it is left to the owner. (The owner chose to keep it, ADR 0045.)

The plume model of next step 3 is in [ADR 0044](0044-plume-agate-as-a-silica-garden.md),
and the iris rhythm of next step 2 in [ADR 0043](0043-a-fast-rhythm-for-iris-agate.md).
