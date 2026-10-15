# agatesim

[![CI](https://github.com/lbillings-pixel/first-app/actions/workflows/ci.yml/badge.svg)](https://github.com/lbillings-pixel/first-app/actions/workflows/ci.yml)

**agatesim** simulates how natural agate forms inside its host rock, at the scale of
a single nodule or seam. By changing environmental and geological conditions over
time, it aims to reproduce each of the classic agate forms (fortification,
waterline, botryoidal, moss, shadow, iris and more) and to show which conditions,
and which proposed formation mechanisms, can produce them.

> **Status: M0 (foundation).** No simulation models yet. See the
> [roadmap](docs/roadmap.md).

## What it reproduces so far

Each target form is a rung on the [archetype ladder](docs/archetypes.md). A form
only counts as reproduced when its quantitative criteria pass in CI.

| Form | Status |
|---|---|
| Fortification, seam, waterline, combined, quartz-centre geode, botryoidal, eye, tube, moss, plume, shadow, iris | pending |

## Approach

- **2D cross-sections first**, with 3D later.
- **Procedural models first** for fast, controllable results. Mechanistic physics
  (reaction–diffusion, phase-field, settling) comes later, behind the same
  interface ([ADR 0003](docs/adr/0003-model-architecture.md)).
- **Competing formation hypotheses are separate, swappable mechanisms**, because
  the science is unsettled ([science notes](docs/science/mechanisms.md)).
- **Every run is reproducible** from its config, seed and code version.

## Getting started

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync                    # create the environment and install everything
uv run agatesim archetypes # list the archetype ladder
uv run pytest              # run the tests
uv run pre-commit install  # check each commit with ruff and pyright
```

## Project layout

```
src/agatesim/        simulation package
  archetypes/        archetype ladder (registry.toml) and its validation
  references.py      reference catalogue validation
tests/               pytest suite
docs/
  adr/               architecture decision records
  science/           literature notes and model rationale
  archetypes.md      generated from the registry; do not edit by hand
  roadmap.md
references/          literature catalogue with checking level and licences
```

## License

Not yet chosen. A license will be added before the repository is made public.
