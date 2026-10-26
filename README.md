# agatesim

[![CI](https://github.com/lbillings-pixel/agatesim/actions/workflows/ci.yml/badge.svg)](https://github.com/lbillings-pixel/agatesim/actions/workflows/ci.yml)

**agatesim** simulates how natural agate forms inside its host rock, at the scale of
a single nodule or seam. By changing environmental and geological conditions over
time, it aims to reproduce each of the classic agate forms (fortification,
waterline, botryoidal, moss, shadow, iris and more) and to show which conditions,
and which proposed formation mechanisms, can produce them.

> **Status.** All thirteen target forms are reproduced at the procedural tier and at the mechanistic tier ([ADR 0035](docs/adr/0035-what-the-mechanistic-tier-requires.md)), shadow agate on a stated, unsourced assumption ([ADR 0048](docs/adr/0048-shadow-agate-by-a-stated-milkiness-link.md)), and eleven run in 3D, judged on cuts (all eleven mechanistically too). See the [roadmap](docs/roadmap.md), the [gallery images](docs/images/) and the [glossary](docs/glossary.md).
>
> agatesim is now complete as a first project: which single mechanisms and conditions can produce which forms. How processes interact within one nodule will be explored in a separate follow-on project ([ADR 0072](docs/adr/0072-reframing-a-coupled-follow-on-project.md)).

![Verification presets of all thirteen forms](docs/images/archetypes.png)

## What we've found

- **Sharp corners point to growth that every part of the wall sees equally.**
  Fortification bands turn corners sharply. On five high-resolution photos of
  polyhedral agates, corners turn within 0.03–0.63 band spacings
  ([ADR 0026](docs/adr/0026-corner-benchmark-from-high-resolution-photos.md)).
  Liesegang rings round them over 1.6–2.4 in 2D
  ([ADR 0015](docs/adr/0015-mechanistic-liesegang.md)).
- **Growth fed by diffusion makes corners lag.** With silica and impurity
  diffusing through the cavity explicitly, front feedback (H1) needs a small
  surface tension to keep its front from breaking up. Its corners then turn as
  sharply as real ones, but they fall behind the faces, so bands thin toward
  them ([ADR 0028](docs/adr/0028-regularised-h1-at-the-corner.md)).
- **Real bands mostly don't thin toward corners.** A marker band followed around
  three of the photos keeps its thickness toward the corners (median 1.02 of
  mid-face, 95% interval 0.92–1.11, against the model's 0.68–0.78), a
  preliminary result
  ([ADR 0029](docs/adr/0029-bands-toward-corners-in-real-agates.md)).
- **Floor layers settle.** Hindered settling reproduces waterline agate, and
  chained with H1 the combined form
  ([ADR 0016](docs/adr/0016-mechanistic-settling.md),
  [ADR 0020](docs/adr/0020-staged-mechanisms.md)).
- **Dendrites by aggregation, enclosed by self-organised bands.** Branched
  inclusions grown by aggregation of diffusing particles, then enclosed by H1
  chalcedony, verify moss agate with nothing about either imposed
  ([ADR 0036](docs/adr/0036-mechanistic-moss.md)).
- **A quartz centre needs no schedule.** In a closed cavity, H1's bands draw
  the dissolved silica down until quartz grows instead; its crystals coarsen
  inward by geometric selection, and an open centre is left when the silica
  runs out ([ADR 0037](docs/adr/0037-mechanistic-quartz-geode.md)).
- **Lobes, eyes and tubes from one rhythm.** H1's self-organised bands,
  grown radiating from nucleation sites on the wall, give botryoidal lobes;
  a brief such stage overgrown by lining gives eyes; lining grown from
  filaments gives tubes
  ([ADR 0038](docs/adr/0038-mechanistic-botryoidal.md),
  [ADR 0039](docs/adr/0039-mechanistic-eye-and-tube.md)).
- **A closed cavity stops the rhythm.** As a closed cavity fills, its silica
  falls and the rejected impurity concentrates, and H1's front stops
  oscillating after a few bands. No parameter set tried keeps visible bands;
  in this model, a well-banded rim needs a cavity still open to fresh fluid
  ([ADR 0037](docs/adr/0037-mechanistic-quartz-geode.md)). A geode resupplied
  until it is 60% full, then closed, has a banded rim (12 bands, against 2
  closed from the start), a clear zone grown after closing, and a quartz
  centre that still coarsens inward
  ([ADR 0046](docs/adr/0046-a-geode-that-bands-while-open.md)).
- **Plumes rise by buoyancy.** Chemical-garden tubes, turned upward by their
  lighter inner solution and branching where their membranes rupture, make
  plume agate once chalcedony encloses them; without buoyancy they don't rise
  ([ADR 0044](docs/adr/0044-plume-agate-as-a-silica-garden.md)).
- **Iris gratings from a fast second rhythm.** The same front feedback, run at a
  much thinner boundary layer, lays regular micro-bands about 2.5 µm apart in
  the clear bands, spaced by how fast the front grew
  ([ADR 0043](docs/adr/0043-a-fast-rhythm-for-iris-agate.md)).
- **Shadow agate, if milkiness switches with the band.** No source links a
  band's growth to its milkiness. Assuming each cycle's fast, impurity-rich
  half is milky and its slow half clear, H1's bands make shadow agate; the
  graded link used before falls short. This is the weakest of the thirteen
  mechanistic verifications
  ([ADR 0048](docs/adr/0048-shadow-agate-by-a-stated-milkiness-link.md)).
- **Stick agate from crystals that came first.** Blade-shaped crystals grown
  from the wall by the quartz crystals' growth law, lined by H1's bands and
  replaced by quartz (or dissolved), give straight pseudomorphs wrapped by
  the bands, in a crevice vein as at Ankara. The one study of the form
  points to a zeolite as the original mineral
  ([ADR 0049](docs/adr/0049-stick-agate.md)).
- **Colour from pigments.** Bands can be coloured by hematite, goethite,
  celadonite, Mn oxide, a violet colour centre, blue scattering or white, as
  the sources describe; procedural models draw from a palette, and H1 carries
  trace iron and manganese through the same front feedback at no measurable
  cost ([ADR 0050](docs/adr/0050-pigments-and-a-palette.md)).
- **A cut changes what you see.** On random cuts through 3D results, bands look
  1.07–1.18 times thicker than they are, and some forms show on only a minority
  of cuts ([ADR 0021](docs/adr/0021-three-dimensional-runs.md)). In 3D the
  mechanistic plume (garden tubes) passes 79% of random cuts and the
  mechanistic geode 77%, against 70% and 76% procedurally
  ([ADR 0047](docs/adr/0047-plume-and-geode-in-3d.md),
  [ADR 0057](docs/adr/0057-a-reproducible-gpu-dendrite-engine.md)). Stick
  agate's tests now hold on a cut at any angle to the sticks (a cut across one
  shows an oval stub as wide as the stick), and 66% and 74% of random cuts pass
  ([ADR 0055](docs/adr/0055-stick-tests-that-survive-the-cut.md)).
- **Dendrite branches have a width, and a cavity caps their length.** The 3D
  dendrites' lattice cell is the finest branch's width, not a numerical step
  ([ADR 0056](docs/adr/0056-dendrite-lattice-spacing-is-branch-width.md)).
  Grown from a flat surface into open space, they follow the length law
  measured for real 3D dendrites, N(L) ~ L^-1.25; inside a closed nodule the
  cavity cuts the longest off, and the exponent stays near 1.7 even with seeds
  1 mm apart. So the model predicts that dendrites in closed agate cavities
  don't follow the fracture-surface law
  ([ADR 0058](docs/adr/0058-dendrite-lengths-in-a-closed-cavity.md)).

These are results within the models tested, not proof of how agate forms.

## What it reproduces so far

Each target form is a rung on the [archetype ladder](docs/archetypes.md). A form
counts as reproduced only when a committed preset passes all of its quantitative
criteria in CI. Each criterion is also tested against results that *lack* its
form, so it can't pass everything. Procedural and mechanistic models are tracked
separately: reproducing a form procedurally says nothing about how it forms in
nature ([ADR 0005](docs/adr/0005-verification-tiers-and-parameter-natures.md)).

| Form | Procedural | Mechanistic |
|---|---|---|
| Fortification | ✅ verified | ✅ verified (H1, boundary-layer approximation) |
| Vein / seam | ✅ verified | ✅ verified (H1, boundary-layer approximation) |
| Waterline | ✅ verified | ✅ verified (H4) |
| Combined fortification and waterline | ✅ verified | ✅ verified (H1 + H4 stages) |
| Banded agate with quartz-crystal centre | ✅ verified | ✅ verified (H1 open, then closed; geometric selection) |
| Botryoidal | ✅ verified | ✅ verified (H1 radiating from nucleation sites) |
| Eye | ✅ verified | ✅ verified (H1 spherulite and lining stages) |
| Tube | ✅ verified | ✅ verified (H1 lining from filaments) |
| Moss / dendritic | ✅ verified | ✅ verified (aggregation, then H1 stages) |
| Plume | ✅ verified | ✅ verified (chemical-garden tubes, then H1) |
| Shadow | ✅ verified | ✅ verified (stated assumption, ADR 0048) |
| Iris | ✅ verified | ✅ verified (H1 with a fast second rhythm) |
| Stick | ✅ verified | ✅ verified (blade crystals, H1 lining, replacement; ADR 0049) |

## Approach

- **2D cross-sections first, then 3D.** A 3D run treats the cavity as a solid and
  is judged on planar cuts, as a collector judges a cut stone
  ([ADR 0021](docs/adr/0021-three-dimensional-runs.md)).
- **Procedural models first** for fast, controllable results. Mechanistic physics
  follows behind the same interface ([ADR 0003](docs/adr/0003-model-architecture.md)):
  front feedback (H1), Liesegang precipitation (H2) and hindered settling (H4).
  H2's rings round off corners, so it fails the fortification test that H1
  passes ([ADR 0015](docs/adr/0015-mechanistic-liesegang.md)). H1 passes it only
  in a boundary-layer approximation
  ([ADR 0017](docs/adr/0017-h1-without-the-boundary-layer.md)); with explicit
  diffusion and a surface state it oscillates, but its corners lag
  ([ADR 0028](docs/adr/0028-regularised-h1-at-the-corner.md)).
- **Competing formation hypotheses are separate, swappable mechanisms**, because
  the science is unsettled ([science notes](docs/science/mechanisms.md)).
- **Every run is reproducible** from its config, seed and code version.
- **Previews show the same agate as full runs.** Geometry is exact and noise is
  defined in world coordinates, not pixels.

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and, for the web app, [Node.js](https://nodejs.org/) 24.

**An NVIDIA GPU (optional)** makes Liesegang precipitation (H2) practical:
`uv sync --extra gpu` installs CuPy, and agatesim then uses the GPU whenever it
finds one (`AGATESIM_GPU=0` declines it), with results the same as on the CPU
([ADR 0054](docs/adr/0054-gpu-by-default-and-progress-for-long-actions.md),
[ADR 0057](docs/adr/0057-a-reproducible-gpu-dendrite-engine.md)). Dendrites
need no GPU: their CPU engine is compiled with Numba, with the same results
([ADR 0061](docs/adr/0061-a-compiled-cpu-dendrite-engine.md)). After that,
run commands as `uv run --no-sync ...` (or `uv run --extra gpu ...`): a plain
`uv run` or `uv sync` removes the GPU extra again. `scripts\start.ps1` keeps it.

### Web app

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1           # Windows: build if needed, then serve
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Rebuild  # after pulling changes
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Gpu      # install and use the GPU extra
```

or on any platform:

```sh
npm --prefix web ci && npm --prefix web run build   # once, and after UI changes
uv run agatesim serve                               # http://127.0.0.1:8000/
```

The app runs only on your machine (bound to localhost). It offers:

- **Start from a form**: pick a form and a tier (procedural or mechanistic) to
  load its verified settings; the live preview is judged as that form as you go.
- **Live preview** that updates as you move sliders.
- **Randomize**: move a model's key settings toward random values within
  bounded ranges (subtle to wild), to explore what it can make; mechanistic
  draws are checked to still band, and can be kept within the chosen form.
  **Undo and redo** step back through any settings change; **Reset** returns
  to the preset, form or run last loaded and counts what differs from it.
- **Cavity menu** of preset shapes for volcanic, sedimentary and seam settings,
  plus a **drawing tool** for your own (click corners or sketch freehand; keep
  corners angular or smooth them).
- **Tubes**: click the preview to place filaments that banding grows around.
- **Specimens screen**: measure your own specimen photos (they stay on your
  machine and are shown without metadata). Mark the ruler, and agatesim traces
  the outline (correcting for the face standing above the ruler), maps the bands,
  checks the forms it can judge from a photo, and fits a simulated replica in the
  specimen's own outline.
- **3D screen**: a cavity as a solid (vesicles, an angular nodule, lobed and
  lumpy nodules, sheet-like seams), a rotatable 3D view opened at a cut, and
  the cut itself as a slab, judged like any 2D result. Tilt and move the cut,
  or survey random cuts to see how often a cut shows the form, then browse the
  cuts as pictures and open any one as the main cut. Opening a saved 3D run
  shows its own saved volume, at its full resolution up to 256³.
- **Optical views**: see the preview as a slab lit from one side (shadow agate:
  move the light and the shadows sweep) or as a backlit thin slice (iris agate:
  change the view angle and direction and the colours shift; any band with
  regular micro-banding diffracts).
- **Parameters** with units and a badge for what kind of quantity each one is:
  physical, effective or imposed. Key settings come first, the rest under
  "More settings"; the colour palette has ready-made choices.
- **Conditions over time**: a timeline editor for silica supply, settling,
  spherulitic growth, dendrite growth, stick crystals and iron, with steps,
  ramps and pulses (growth-history model).
- **Band statistics** for each result, side by side with a pinned run.
- **Full-resolution runs** in the background, saved to `runs/`.
- **Progress for long actions**: building a 3D view, surveying cuts, full runs,
  slow previews and Randomize show what they are doing, how far they have got
  and roughly how long is left, with **Cancel**; work you abandon stops. An
  amber **caution badge** warns beforehand of an action estimated to take over
  30 seconds or 2 GB of memory, and a preview that heavy waits for a press of
  **Build it** instead of starting by itself
  ([ADR 0062](docs/adr/0062-heavy-previews-wait-saved-3d-views-and-cut-browsing.md)).
- **Saved runs** can be deleted from either run list; both show how much space
  the runs folder takes.
- **Run browser and slab viewer** with zoom, pan, a scale bar, a growth slider
  that shows the agate forming over time (play, pause, speeds and looping), and
  side-by-side comparison. On the 3D screen the same control animates the cut
  and the 3D view together.

### Command line

```sh
uv sync                                   # create the environment
uv run agatesim presets                   # shipped run presets
uv run agatesim cavities                  # preset cavity shapes
uv run agatesim run fortification         # full run -> runs/<run-id>/
uv run agatesim run waterline --preview   # quick 256 px preview
uv run agatesim run my-config.toml        # your own configuration
uv run agatesim archetypes                # the archetype ladder and its status
uv run agatesim volume presets            # shipped 3D presets
uv run agatesim volume run fortification-mechanistic-3d --survey 60   # 3D run + random cuts
uv run agatesim volume survey waterline-3d --cuts 100                 # judge random cuts only
```

Each run directory contains `config.toml` (reproduces the run exactly),
`metadata.json` (code version, seed, library versions), `fields.zarr` (material
fields), `slab.png` (rendered slab) and `metrics.json` (archetype criteria).

## Development

```sh
uv run pytest                             # tests
uv run ruff check; uv run ruff format     # lint and format
uv run pyright                            # strict type checking
uv run pre-commit install                 # run checks on every commit
uv run python scripts/make_gallery.py     # regenerate docs/images
uv run python scripts/regression_hashes.py --write before.json   # before a refactor...
uv run python scripts/regression_hashes.py --check before.json   # ...and after: results unchanged?

npm --prefix web run dev                  # UI dev server with hot reload (proxies /api to :8000)
npm --prefix web test                     # UI unit tests (Vitest)
npm --prefix web run lint                 # ESLint
```

## Project layout

```
src/agatesim/
  archetypes/        archetype ladder (registry.toml): criteria and thresholds
  presets/           shipped run configs; one per verified archetype
  models/            formation models: procedural (fortification, waterline, growth history)
                     and mechanistic (front feedback H1, Liesegang H2, settling H4,
                     stages, chemical gardens), pigments and palettes
  criteria/          measurements that judge results against the ladder
  geometry.py        cavity shapes, exact masks and wall distances
  config.py          run configuration (TOML)
  simulate.py        run a configuration
  render.py          slab rendering in diffuse reflected light
  optics.py          optical views: shadow (reflected light) and iris (backlit slice)
  explore.py         Randomize: key settings drawn within bounded ranges
  progress.py        progress and cancellation for long work
  _rd.py, _dla.py    GPU-or-CPU solvers: Liesegang reaction-diffusion, dendrite aggregation
  _dla_numba.py      the dendrite aggregation's compiled CPU loop
  runs.py            run records
  specimen/          photo analysis: scale, outline, observed fields, identification, replica
  volume/            3D runs: solids, models evaluated at points, cuts, random-cut surveys
  server/            FastAPI backend for the web app (`agatesim serve`)
web/                 React + TypeScript web app (built into server/static)
scripts/             gallery generator, Windows start script, H1 analysis and 2D front solver,
                     photo measurements, regression hashes, dendrite studies
tests/               pytest suite, including negative controls for every criterion
docs/
  adr/               architecture decision records
  glossary.md        plain-language meanings of the terms used
  science/           literature notes and model rationale
  archetypes.md      generated from the registry; do not edit by hand
  images/            generated by scripts/make_gallery.py
references/          literature catalogue with checking level and licences
```

## License

[MIT](LICENSE). Literature and reference material keep their own licences; see
[references/](references/README.md).
