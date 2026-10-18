# 51. Randomize, and a lighter app

- Status: accepted (owner approved the list, 2026-10-18)
- Date: 2026-10-18
- Builds on: [ADR 0003](0003-model-architecture.md), [ADR 0035](0035-what-the-mechanistic-tier-requires.md), [ADR 0050](0050-pigments-and-a-palette.md)

## Context

The owner asked for a polish pass on the web app that removes or combines as
well as adds, and for a Randomize feature that lets key settings vary to
explore a wider variety of results, bounded so they don't run into
nonsensical regimes. A survey of the app found: a "Compare mechanisms" panel
built for the corner question (closed, ADR 0034); stale "shadow pending" text
on the Two ways screen; long settings lists (52 settings and 6 timelines for
the growth model, 83 for the staged model); a flat menu of 29 presets beside
a separate "Judge as" list; a run-name box most people never need.

## Decision

1. **Explore ranges.** A model setting may carry a bounded `explore` range
   (`agatesim.params.param`, on a log scale where useful), chosen to keep the
   model in its working regime and always inside the setting's own limits (for
   H1, catalysis 14–30, the window where its rhythm oscillates; the palette's
   weights 0–1). A setting with a range, or marked `key`, is a **key setting**.
   H2 (Liesegang) has none: checking a draw would need the GPU.
2. **Randomize** (`agatesim.explore`, `POST /api/randomize`): each key setting
   with a range moves toward a value drawn from it, by a strength from 0.2
   ("subtle") to 1 ("wild"), and the seed changes. Values stay within the
   range's span (or the current value, if that lies outside) and the setting's
   limits, so nothing runs away. Cavity, schedules and choices are kept.
   - **Checked draws.** A mechanistic draw is checked with a quick 192 px run
     and redrawn if it lays fewer than 4 bands (H1's rhythm can stop away from
     its regime: about half of fully random H1 draws do). With "stay within
     the form", any model's draw must also pass the judged form's tests, at the
     form's own resolution (up to 768 px; corners need it). Up to 12 tries,
     else the settings are left unchanged and the app says why.
3. **Undo and redo** of any settings change (50 steps; changes closer than
   0.7 s, a slider drag, undo as one).
4. **Key settings first.** The settings panel shows key settings and puts the
   rest under "More settings". A nested model with ready-made values (the
   palette: "Red and yellow", "Blue and white", "Green", "Black and white",
   "Violet", "Mixed", "Iron (as before)") offers them in a menu.
5. **One form chooser** replaces the preset menu and "Judge as": choosing a
   form loads its verification preset for the chosen tier (procedural or
   mechanistic) and judges the result as that form; the few other presets sit
   under "Other presets". Models are grouped as procedural and mechanistic.
6. **Removed:** the Compare mechanisms panel (the Two ways screen compares the
   tiers), the run-name box (names follow the model and cavity, as before when
   left alone), a duplicated actions row. Stale copy fixed in Two ways and the
   tour. The Specimens screen stays (owner decision).

## Results

- Randomize returns in well under a second for procedural models and in a few
  seconds for mechanistic ones; "stay within the form" for mechanistic H1 at
  medium strength succeeds on about 4 draws in 10 (about 10 s on average).
- Bounds hold: over 25 fully random draws of five presets every value stays in
  its range and limits (a test); zero strength changes only the seed.
- Checked in the browser: form chooser and tiers, grouped models, key settings
  with "More settings", Randomize (procedural and checked mechanistic), Undo
  restoring the exact values, Redo, palette presets.
- Tests: `tests/test_explore.py` (10), web tests for the form helpers, key
  settings and preset matching (83 web tests in all).

## Consequences

- New key settings need a range chosen with care; a range that strays outside
  a mechanistic model's regime shows up as more redraws, not as wrong results.
- Randomized results are explorations, not verifications: only committed
  presets verify a form.
