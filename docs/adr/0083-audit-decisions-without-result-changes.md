# 83. Audit decisions that leave results unchanged

- Status: accepted (owner, 2026-11-10: "all as recommended" for audit part C)
- Date: 2026-11-10
- Builds on: [ADR 0003](0003-model-architecture.md) (parameter natures),
  [ADR 0004](0004-archetype-ladder.md) (changing verified criteria needs an ADR),
  [ADR 0034](0034-closing-the-corner-question.md) (the corner question, closed)
- Audit: PR #14, part C items 3–5, 9–13, 15, 16, 18–32

## Context

The 2026-11 audit (PR #14) listed 32 decisions for the owner. The owner accepted
every recommendation. This ADR records the ones that change no simulation result,
done in one batch. Those that change results (items 1, 2, 6, 7, 8, 14, 17) get
their own records.

## Decisions

**Behaviour and the app**

- **C3:** the staged model with tube filaments is refused with a clear message
  (no shipped preset combines them; its later stages don't grow around tubes).
- **C4:** a nested model can name settings its parent `ignores`; the app hides
  them. Staged's wall ignores `micro_rhythm` and its boundary layer, which it
  never carried through.
- **C5:** a survey with no archetype reports the thickness ratio it measured.
- **C9:** the live 3D survey uses the run's seed and the saved-run survey size
  (512 px, or a form's minimum), and its estimate uses the same size, so a live
  survey and a saved run's survey of the same settings give the same pass rates.
  Estimated cost of 40 cuts: 11 → 20 s for most presets, 32 → 56 s for moss;
  memory unchanged. The caution badge now shows for botryoidal and plume surveys
  too (over 30 s).
- **C10:** an optical view is shown only for the settings and light it was made
  for; otherwise the plain slab, until the new one arrives. Changing the angle
  keeps the last view meanwhile, so dragging doesn't flicker.
- **C11:** the 3D and Specimens screens stay mounted once opened, so leaving one
  keeps its state, including a running job's progress and Cancel. The 3D
  screen's settings now use their own element ids (`volume-param-…`), since the
  simulator's panel is mounted alongside (found in the browser check).

**Rules and wording**

- **C12:** `band-count`'s negative controls (H1 without its feedback) moved to
  `tests/test_criteria.py`, as the rule asks.
- **C13:** CLAUDE.md says the GPU-vs-CPU tests skip in CI.
- **C15:** the run's gravity direction counts as geometry, which criteria may read.
- **C16:** wording only, no threshold or measure changed: `lobe-count` now
  describes what the code counts (bulging stretches divided by cusps, as ADR 0008
  says); the tube ring zone says 0.4 of the gap, as the code uses; the registry
  header no longer calls every metric provisional.
- **C18:** the commit hooks run `uv run --no-sync`, so they keep CuPy.
- **C19:** `starlette`, imported directly, is a declared dependency.

**Docs**

- **C20–22:** `docs/science/mechanisms.md` updated: H1 with explicit diffusion
  per ADR 0017's amendments; iris spacing from Jones's measured gratings (ADR
  0042), and that open question answered; the status block's counts; stale notes;
  the later plume, stick and pigment models. Refractive index: the owner
  supplied Graetsch, Flörke & Miehe 1987, whose Table 6 gives 1.533–1.542 along
  the fibres for Brazilian agate chalcedony, falling with water content
  [@graetsch1987]. n = 1.54 lies in that range and stays, now sourced; results
  are unchanged.
- **C23:** forward notes in ADRs 0010, 0015, 0024, 0049, 0053 and 0073; ADR 0072
  records that the new project is Nodule.
- **C24:** the roadmap gains a row for the work since v0.1.0; README lists the
  Specimens screen's tabs and the library, classify, maps and `volume shape`
  commands.
- **C25:** `references/README.md` describes the quality gate and the library files.
- **C26:** catalogue entries never cited removed: `oehler1976`, `raman1955`, and
  `darcet2024`, a duplicate of `darcet2023` whose notes were merged into it.

**Removed (git keeps them; commit 15c36be is the last that has them)**

- **C27:** the corner-question research code: `scripts/h1_stefan_scan.py`,
  `h1_linear_stability.py`, `h1_surface_stability.py`,
  `h1_regularised_stability.py`, `h1_front_2d.py`, `marker_band_thinning.py`,
  `fetch_reference_images.py`, the module `agatesim.specimen.corner_fit` (used only
  by its tests and those scripts) with its tests, and
  `references/images/corner_marks.toml`. ADR 0034 and the ADRs that cited them
  carry a record note.
- **C28:** `scripts/dendrite_convergence.py` and `dendrite_length_law.py` (notes
  in ADRs 0056, 0058).
- **C29:** `scripts/rim_check.py` kept; it now says so plainly when no Nodule
  checkout sits beside this repository.
- **C30:** unused code removed: `VolumeSimulation.cut_plane`, `GET /api/jobs` and
  `JobManager.all`, `Observation.crop` and `.band_count`, `Schedule.values`,
  `Step.start`, the `most` parameter of a saved run's voxels (its test now calls
  `read_volume_view` directly), the library label `DELETE` endpoint and its web
  call, the web `encodeGif` (now a test helper), `growth._drop_retired` and its test (no
  saved run on the owner's PC carries the retired setting), and `docs/images/cavities.png`
  with its generation. **Kept:** `orbit.rayBox` and `orbit.keptSegment`. They are
  the tested reference for the 3D view's shader, which mirrors them.
- **C31:** `.gitignore` drops entries for tools the project doesn't use; `.vscode/`
  stays ignored.
- **C32:** web wording: the criteria panel no longer names a "Judge as" control;
  the statistics note says the Specimens screen measures photos the same way;
  "· scaled" shows only when a ruler is marked (a new `scaled` flag).

## Consequences

- No simulation result changes; regression hashes are unaffected.
- Staged's schema gained the `ignores` hint, so the cut-shapes cache for staged
  presets is recomputed on the next `agatesim volume shape`; that run is due
  anyway after the result-changing decisions.
