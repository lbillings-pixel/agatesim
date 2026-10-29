# 75. Rim outlines are measured only after a helper's yes

- Status: accepted (2026-10-29; owner's choice after the held-out check)
- Date: 2026-10-29
- Builds on: [ADR 0073](0073-rim-finder-for-library-photos.md), [ADR 0074](0074-rim-finder-option-c-segmentation-model.md)
- Changes: how ADR 0073's bar is used (section 3)

## Context

Option C missed ADR 0073's bar on the 150 held-out photos (ADR 0074 section
6). With the owner's check counted (32 outlines: all twelve the helpers
failed and 20 they passed, shown blind):

- outlines that follow the rim: 75 of 88 (85%; bar 90%), missed;
- an outline on 83 of 115 photos with the rim in frame (72%; bar 60%), met;
- cut-off photos declined: 30 of 35 (86%; bar 90%), missed. The owner judged
  two more rims not visible as a whole (grass across the stone, a backdrop as
  dark as the rind), and the finder had outlined both.

The owner agreed with the helpers on 29 of the 32. The owner passed one the
helpers failed (a bookend pair) and failed two they passed (a loop into a
shiny stand, a thin strip left out at the upper left). So 2 of the 20 helper
"yes" outlines were wrong by the owner's standard: about 1 in 10, with a wide
range at that sample size (95% Wilson interval about 3% to 30%).

ADR 0074 ruled out further tuning: the held-out set would stop being a test,
and the library has no other unseen photos.

## Decision

1. Nodule measures a rim outline only after a helper agent has judged that
   very outline: the whole rim in the frame, and the outline following it.
   Outlines judged "no", and photos without an outline, are not measured.
   Where the owner has answered, the owner's answer replaces the helper's.
2. A judgment belongs to the outline it was made on (the agatesim commit and
   settings that drew it). A changed outline needs a new judgment.
3. Nodule reports, alongside any measure built on these outlines, how many
   outlines were used and the estimated share that are wrong by the owner's
   standard (2 of 20 owner-checked helper passes, so far).
4. The owner's time is not needed for each outline (option offered and
   declined: the owner confirms every helper pass, about an hour for the
   library).

## Consequences

- With the judgments made so far, nodule has helper-passed outlines on 76 of
  the 150 held-out photos (75 after the owner's answers), 36 of the 80 tuning
  photos and 15 of the friend's 21 outlines. Where the verdicts live, and how
  nodule matches them to the outlines it draws, is decided in nodule.
- Measures on rim outlines carry about a 1-in-10 chance per photo of a wrong
  outline (perhaps 3% to 30%). Measures that a wrong outline moves strongly
  should be read with that in mind, or checked by the owner photo by photo.
- The split-stone failure (two halves in one outline) is common in the
  friend's photos. Those outlines are mostly judged "no", so the friend's set
  contributes fewer photos.
- B stays the fallback where the model is not fetched. Its outlines need
  their own judgments under point 2.
