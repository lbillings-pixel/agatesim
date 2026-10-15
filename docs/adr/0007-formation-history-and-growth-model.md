# 7. Formation history: schedules and the procedural growth model

- Status: accepted
- Date: 2026-10-15

## Context

Many agates record a sequence of conditions, not a single state. Examples are
a wall-parallel rim followed by horizontal floor layers, or banding that gives way
to coarse quartz as silica supply falls ([@lu1994], [@goetze2020]). The M1 models
have no notion of time beyond deposition order, so they can't express these
sequences. The owner chose a timeline editor in the UI, and the Artigas-like
order (fortification first, then waterline) as the default combined preset.

## Decision

1. **Formation time τ ∈ [0, 1].** Every run spans normalized formation time. It is
   not calibrated to years. Mechanistic models (M8) will map it to physical time.
2. **Schedules.** A scheduled condition is a base value plus steps, ramps and
   pulses (`agatesim.schedules`). The same rules are implemented in Python and
   in the UI (for the timeline plot), and both are pinned to one shared fixture,
   `tests/fixtures/schedules.json`.
3. **The `procedural-growth` model** has three scheduled conditions:
   - *silica* sets the deposition rate. Below `quartz_threshold`, macrocrystalline
     quartz grows instead of chalcedony.
   - *settling* chooses the mode. Below 0.5 material lines all surfaces of the
     open space; at 0.5 or above it settles into horizontal floor layers, with
     the area it deposits conserved.
   - *iron* sets band staining.

   Time is split into stages wherever the mode changes. Each stage is solved in
   closed form: a distance transform for wall-lining, or a height ordering for
   settling. Bands are periods of formation time.
4. **Quartz crystals.** Crystal seeds are placed in world coordinates with a
   density that falls with distance grown, so crystals coarsen inward. A new
   `grain` field carries crystal ids.
5. **Criteria from fields alone.** The combined form classifies each band as
   horizontal, wall-parallel or other from its geometry. Its tests are
   `two-domains` (at least 3 bands in each domain) and `staged` (at most 4
   uninterrupted runs). The quartz geode's tests are `phase-transition`,
   `inward-coarsening` and `quartz-last`.

   Whether the result follows the *configured* schedule is checked in tests, not
   in the criteria, because a photo has no schedule. The stage-order test covers
   the combined form, and the supply-sensitivity test checks that an earlier drop
   in silica supply moves the quartz outward.
6. **Old models stay.** `procedural-fortification` and `procedural-waterline`
   remain the verification presets for their forms. A cross-model test checks
   that wall-only growth also passes the fortification criteria.

## Consequences

- The UI gains a timeline editor for every scheduled variable. New scheduled
  variables appear there automatically.
- The quartz threshold encodes the common reading that falling silica
  supersaturation favours macrocrystalline quartz. We haven't yet confirmed this
  in a source checked at full-text level, so the parameter is labelled
  *effective* and the science notes say so.
- Simplifications to revisit:
  - Quartz crystals are equant cells rather than elongated, inward-pointing
    prisms, and the open space has a smooth margin rather than crystal
    terminations.
  - All pockets of open space settle to a single level.
  - Wall-lining after the first stage uses a pixel distance transform (half-pixel
    accuracy).
