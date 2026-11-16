# 85. Halos that clear only partly

- Status: accepted (owner, 2026-11-15: "We need faint banding inside; I approve agatesim
  changes for this", from Nodule)
- Date: 2026-11-15
- Builds on: [ADR 0079](0079-plumes-traced-tilted-tinted-and-haloed.md) (clear halos),
  [ADR 0078](0078-band-material-varying-along-bands.md) (the steps' own values are kept),
  [ADR 0072](0072-reframing-a-coupled-follow-on-project.md) (changes Nodule needs)
- Spec: Nodule's ADR 0018 section 14

## Context

A halo (ADR 0079) erases the band colour within its width of a plume and makes the
chalcedony there as clear as quartz. Nodule's moss probe used halos on every strand as
the clear sheath in which moss sits. The owner judged the look right in direction, but
asked that the sheath be "clear, weakly banded", not blank: a wholly clear halo removes
every band inside it.

The sources support a clear sheath round moss filaments [@akahane2025; @goetze2020b] and
clear halos round plumes that erase earlier bands [@kile2002, p. 263] (*plausible*). None
says how completely a halo clears, so the degree is an assumption chosen for the look.

## Decision

1. **`dendrite_halo_clearing`** (3D, `effective`, default 1, range (0, 1]): the share of
   the band colour a halo erases, and of the way to clear chalcedony it goes. The halo's
   weight at each point (1 inside, fading over the outer `HALO_EDGE`) is multiplied by it.
   Below 1, bands inside a halo keep `1 - clearing` of their colour and of their
   cloudiness.
2. **Assumption:** one value for every halo of a stone, the same for colour and for
   translucency. No source gives one.

## Consequences

- Default results are unchanged: at 1 the weight is multiplied by exactly 1.
- No run-time cost (one multiplication per evaluated chunk).
- Test: `test_partial_clearing_leaves_faint_bands_in_halos` (at 0.7, coloured bands near
  plumes keep a tenth to six tenths of their colour). Negative control: a wholly clear
  halo keeps none and is rejected.
- Not a formation claim: the parameter shapes a look. Whether real sheaths are faintly
  banded because earlier bands were partly erased, or because later silica was laid down
  nearly clear, is open.
