# 54. The GPU by default, and progress for long actions

- Status: accepted (owner request, 2026-10-18)
- Date: 2026-10-18
- Follows: [ADR 0015](0015-mechanistic-liesegang.md), [ADR 0027](0027-liesegang-in-3d.md), [ADR 0051](0051-randomize-and-a-lighter-app.md)

## Context

The owner chose Liesegang precipitation (H2) on the 3D screen and saw only
"Building the 3D view…" with no sign of progress. Two causes:

1. **The GPU was off unless asked for.** The solver used CuPy only with
   `AGATESIM_GPU=1` in the environment. The app, started from a desktop
   shortcut without it, ran H2 on the CPU, which takes hours for the 3D
   preset (about 100 s on the GPU).
2. **Long actions said nothing about their progress.** The app waited on one
   request with no way to know how far it had got, and an abandoned request
   (a setting changed meanwhile) kept running on the server and held up the
   next build, since 3D preparations run one at a time.

The owner asked that an available GPU always be used for H2, and for a
real-time status indicator, with the share done and the time left, for any
action likely to take more than about 10 seconds.

Measured on the owner's machine (RTX 4070), building the 3D view takes: H2
97 s; moss, plume and their mechanistic versions 12–20 s; every other 3D
preset under 10 s. A survey of 40 random cuts takes 40–180 s, a full 3D run
minutes, and Randomize with "stay within the form" up to tens of seconds.

## Decision

1. **The GPU whenever CuPy finds one.** `agatesim._rd.array_module` uses CuPy
   if a GPU is usable, unless `AGATESIM_GPU=0`. Results agree with NumPy to
   rounding, as before. The H2 model's title in the app says which it uses:
   "on the GPU" or "no GPU found, so slow".
2. **Progress reporting** (`agatesim.progress`). Long loops call
   `report(fraction, label)`, which does nothing outside a tracked task, so
   models, tests and the command line are unchanged. Parts of the work map
   onto shares of the whole (`span`), weighted by a rough guess at their
   time. Reports:
   - **H2** (2D and 3D): the depth the incoming metal has reached (the
     solver's own stopping test, 5% of the reservoir) over the deepest
     cell's depth, squared, since a diffusing front's depth grows as the
     square root of time. Measured at most four times a second, on the GPU.
     The 3D lattice's setup is its own labelled part.
   - **Stages** of the 3D growth and staged models, named ("Branched
     inclusions", "Chemical-garden tubes", "Banded wall (H1)"…); within them,
     the inclusions' wall-distance pass and aggregation (cells attached over
     the budget), and the garden's tube built over its budget.
   - **Surveys** by cut, **full runs** by stage, and **Randomize** by draw
     (no share: a search that stops at the first good draw can't say).
3. **The time left** follows the recent rate of progress (over 15 s, or a
   quarter of the run if longer), so a slow start such as setting up doesn't
   skew it; it is shown once 3% is done and 2 s have passed.
4. **Cancellation.** A cancelled task stops at its next report. The app
   names each long request's task (`X-Progress`), reads
   `GET /api/progress/{id}` twice a second, and sends `DELETE` when it stops
   waiting: on Cancel, or when a newer setting replaces the request. A 3D
   preparation shared by the view and its cut stops only when both have given
   up. Cancelled work answers 409; a cancelled full run ends as "cancelled".
5. **The app** shows a bar once an action has run for a second: what it is
   doing, the share done, roughly how long is left and the time so far, with
   Cancel: building the 3D view and its cut (shown over the view), surveys,
   full 2D and 3D runs, the 2D preview and Randomize. A stopped build offers
   Rebuild.

## Results

- **H2 in 3D on the GPU** (liesegang-nodule-3d, 97 s): the bar moves almost
  evenly through the run; 10 s in it estimated 83 s left (87 s actual), and
  thereafter within about 10 s. Cancel stops the server-side run within a
  second, and the next build starts at once (0.8 s for a fast preset after
  cancelling H2).
- **Changing the preset mid-build** frees the server: the new build finished
  1.5 s later.
- **Moss and plume** report through their slow steps; the estimate can run
  short near the end of the aggregation, which slows as it finishes.
- **Nothing else changes.** All 2D presets (H2's GPU-sized two skipped) and
  all 3D presets except H2 hash bit-identical before and after, run on the
  CPU; tracking a run doesn't change its result (a test).
- **Phone width:** the 3D screen now stacks in one column (its own column rule
  had overridden the phone layout); the bar fits the view.
- Tests: `tests/test_progress.py` (17), `web/src/lib/progress.test.ts`.

## Consequences

- Locally, tests and runs that use H2 now run it on the GPU when CuPy is
  installed; CI has no GPU and is unchanged.
- Some steps hold Python's global lock for up to 2–3 s at a time (large array
  passes at the start of a stage), so the bar can pause briefly before
  catching up.
- New long loops should call `progress.report`; a step that reports nothing
  shows as a pause in the bar, not as an error.

## Amendment (2026-10-18): a faster distance to an ellipsoid's wall

The moss, plume and botryoidal 3D builds spent most of their time on the exact
distance from points inside an ellipsoid to its surface: 52 bisection steps
per point, about 3.4 µs each, over 2–3 million points per build. The owner
asked for the faster method proposed at the check-in.

- **Newton's method on a better-shaped equation.** The nearest surface point
  is fixed by the one root t of S(t) = Σ (a_i p_i / (t + a_i²))² = 1 above
  −min(a)². Newton's method on S itself converges slowly near the centre (S
  has a pole there). On h(t) = S^(−1/2) − 1 it doesn't: S^(−1/2) is a power
  mean of the straight lines (t + a_i²) / (a_i p_i), so h is concave,
  increasing and nearly straight. Started below the root, where the shortest
  axis's term alone equals 1, the steps climb to the root without
  overshooting: about 5 steps, at most 12 in a million random points.
- **Accuracy:** at the points where the two methods differed most, Newton
  matched a brute-force search over the surface to 1e-10 mm, and the old
  bisection was off by up to 4e-9 mm. A test checks the centre, the shortest
  axis's plane, points just inside the wall, a sphere and an oblate spheroid.
- **Speed** (CPU, preparing the formation): moss 13.7 → 4.5 s, moss
  (mechanistic) 14.0 → 5.0 s, plume 19.2 → 10.5 s (the rest is the
  aggregation itself), plume (mechanistic) 12.5 → 8.7 s, botryoidal 7.0 →
  3.8 s, eye 6.4 → 3.6 s, tube (mechanistic) 4.3 → 1.7 s.
- **Results:** 17 of the 20 3D presets (H2 left out) are bit-identical in every
  field of a 96³ volume and the configured cut. In the other three, staged
  presets with an H1 wall (eye, fortification-then-waterline and plume, all
  mechanistic), band, phase and crystal fields are identical; the impurity
  stain moves by up to 0.006 and the deposition time by up to 0.0001, since
  H1's history follows the wall-distance distribution, which moved in its
  last digits. No judged field changed.
