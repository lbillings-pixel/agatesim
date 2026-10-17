# 36. Moss agate at the mechanistic tier

- Status: accepted
- Date: 2026-10-17
- Builds on: [ADR 0009](0009-branched-inclusions.md), [ADR 0020](0020-staged-mechanisms.md), [ADR 0035](0035-what-the-mechanistic-tier-requires.md)

## Context

ADR 0035 found moss the cheapest form to take to the mechanistic tier. Its
dendrites already grow by aggregation of diffusing particles, but the
chalcedony that encloses them came from the procedural growth model, whose
bands are imposed.

## Decision

1. **A dendrite stage in the staged model.** `order = "dendrite-wall"` grows
   branched inclusions from the cavity wall, then an H1 wall stage fills the
   rest of the cavity. The wall stage grows from every solid surface, so the
   chalcedony follows each branch. The stage reuses the aggregation of
   ADR 0009 (`grow_inclusions`, factored out of the growth model with results
   unchanged: all 17 2D presets hash identically).
2. **Its parameters** (`[model.dendrite]`): site spacing, particle
   concentration, amount, sticking chance and branch width, all `effective`.
   The upward preference and start height of the procedural model are left
   out: they are the plume stand-in ADR 0035 rules out. The inclusion mineral
   (`tint`, which only sets its colour) is `physical` here: it names a
   measurable composition rather than a property of the pattern.
   The procedural model's `dendrite_tint` was relabelled `physical` to match
   (it had been `imposed`).
3. **What is and isn't explained.**
   - Process: dendrites as aggregation of diffusing particles that attach to
     the growing branches, supported for Mn-oxide dendrites in 3D
     [@hou2023] and as DLA [@chopard1991] (abstract only).
   - Imposed: the order of the stages (dendrites, then chalcedony), as for the
     combined form (ADR 0035, rule 2).
   - Linking assumption: the dendrites grow into open fluid before the
     chalcedony, as ADR 0009 already assumed. Dendrites that grow later in a
     gel or along fractures, and the green filamentous kind of moss agate
     ([@goetze2020b]), aren't modelled.
4. **Verification preset** `moss-mechanistic`, with the same cavity, seed and
   dendrite values as the procedural preset.
5. **Rule 1 in CI.** `tests/test_criteria.py` now checks that no mechanistic
   verification preset's model has an `imposed` parameter, with a check that
   the test finds the procedural model's imposed ones.

## Results

- `moss-mechanistic` passes: fractal dimension 1.48 (26 inclusions, range
  1.3–1.9), inclusions 7.8% of the cavity (at most 20%). The procedural preset
  gives 1.45 and 7.8%.
- The cavity fills completely; every inclusion predates every chalcedony
  band, and H1 lays down its bands around every branch.
- Preview and full run: the inclusion share at 384 px is within 1% of 768 px.
  At 256 px it rises to 11%, because pixels coarser than the 0.12 mm branches
  widen them; the procedural model does the same.
- No new criterion, so no new negative control; moss's existing negative
  controls apply unchanged.

## Consequences

- Mechanistic tier: 5 of 12 forms.
- The H1 chalcedony is rendered with H1's own staining, so this moss agate
  looks more strongly banded and coloured than the procedural one. Tuning H1
  to look clearer would be fitting the picture, not the mechanism.
- 3D staged runs reject dendrite stages for now; the 3D growth model's
  aggregation could be wired in later.
- Plume can reuse the dendrite stage once a sourced process makes growth
  directional (ADR 0035).
