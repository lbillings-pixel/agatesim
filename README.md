# agatesim

[![CI](https://github.com/lbillings-pixel/agatesim/actions/workflows/ci.yml/badge.svg)](https://github.com/lbillings-pixel/agatesim/actions/workflows/ci.yml)

**agatesim** simulates how natural agate forms inside its host rock, at the scale of
a single nodule or seam. By changing environmental and geological conditions over
time, it aims to reproduce each of the classic agate forms (fortification,
waterline, botryoidal, moss, shadow, iris and more) and to show which conditions,
and which proposed formation mechanisms, can produce them.

> **Status: M12 done: ten of the twelve forms also run in 3D, judged on cuts ([cuts](docs/images/volume.png)). All twelve target forms reproduced at the procedural tier; fortification, seam, waterline and the combined form also at the mechanistic tier (H1 front feedback, H4 hindered settling, and the two chained). See [mechanisms](docs/images/mechanisms.png).** See the [roadmap](docs/roadmap.md).

![Verification presets of all twelve forms](docs/images/archetypes.png)

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
| Banded agate with quartz-crystal centre | ✅ verified | pending |
| Botryoidal | ✅ verified | pending |
| Eye | ✅ verified | pending |
| Tube | ✅ verified | pending |
| Moss / dendritic | ✅ verified | pending |
| Plume | ✅ verified | pending |
| Shadow | ✅ verified | pending |
| Iris | ✅ verified | pending |

## Approach

- **2D cross-sections first, then 3D.** A 3D run treats the cavity as a solid and
  is judged on planar cuts, as a collector judges a cut stone
  ([ADR 0021](docs/adr/0021-three-dimensional-runs.md)).
- **Procedural models first** for fast, controllable results. Mechanistic physics
  follows behind the same interface ([ADR 0003](docs/adr/0003-model-architecture.md)):
  front feedback (H1), Liesegang precipitation (H2) and hindered settling (H4).
  H2's rings round off corners, so it fails the fortification test that H1
  passes ([ADR 0015](docs/adr/0015-mechanistic-liesegang.md)). H1 passes it only
  in a boundary-layer approximation. With explicit diffusion its front doesn't
  oscillate, so it makes no bands
  ([ADR 0017](docs/adr/0017-h1-without-the-boundary-layer.md)).
- **Competing formation hypotheses are separate, swappable mechanisms**, because
  the science is unsettled ([science notes](docs/science/mechanisms.md)).
- **Every run is reproducible** from its config, seed and code version.
- **Previews show the same agate as full runs.** Geometry is exact and noise is
  defined in world coordinates, not pixels.

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and, for the web app, [Node.js](https://nodejs.org/) 24.

### Web app

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1           # Windows: build if needed, then serve
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Rebuild  # after pulling changes
```

or on any platform:

```sh
npm --prefix web ci && npm --prefix web run build   # once, and after UI changes
uv run agatesim serve                               # http://127.0.0.1:8000/
```

The app runs only on your machine (bound to localhost). It offers:

- **Live preview** that updates as you move sliders, judged against the chosen
  archetype as you go.
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
  or survey random cuts to see how often a cut shows the form.
- **Optical views**: see the preview as a slab lit from one side (shadow agate:
  move the light and the shadows sweep) or as a backlit thin slice (iris agate:
  change the view angle and the colours shift).
- **Parameters** with units and a badge for what kind of quantity each one is:
  physical, effective or imposed.
- **Conditions over time**: a timeline editor for silica supply, settling,
  spherulitic growth, dendrite growth and iron, with steps, ramps and pulses (growth-history model).
- **Band statistics** for each result, side by side with a pinned run.
- **Full-resolution runs** in the background, saved to `runs/`.
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

npm --prefix web run dev                  # UI dev server with hot reload (proxies /api to :8000)
npm --prefix web test                     # UI unit tests (Vitest)
npm --prefix web run lint                 # ESLint
```

## Project layout

```
src/agatesim/
  archetypes/        archetype ladder (registry.toml): criteria and thresholds
  presets/           shipped run configs; one per verified archetype
  models/            formation models (procedural fortification, waterline, growth history)
  criteria/          measurements that judge results against the ladder
  geometry.py        cavity shapes, exact masks and wall distances
  config.py          run configuration (TOML)
  simulate.py        run a configuration
  render.py          slab rendering in diffuse reflected light
  optics.py          optical views: shadow (reflected light) and iris (backlit slice)
  runs.py            run records
  specimen/          photo analysis: scale, outline, observed fields, identification, replica
  volume/            3D runs: solids, models evaluated at points, cuts, random-cut surveys
  server/            FastAPI backend for the web app (`agatesim serve`)
web/                 React + TypeScript web app (built into server/static)
scripts/             gallery generator, Windows start script
tests/               pytest suite, including negative controls for every criterion
docs/
  adr/               architecture decision records
  science/           literature notes and model rationale
  archetypes.md      generated from the registry; do not edit by hand
  images/            generated by scripts/make_gallery.py
references/          literature catalogue with checking level and licences
```

## License

[MIT](LICENSE). Literature and reference material keep their own licences; see
[references/](references/README.md).
