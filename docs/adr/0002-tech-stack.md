# 2. Technology stack

- Status: accepted
- Date: 2026-10-14

## Context

- The project's eventual audience is researchers, who mostly read and run Python.
- Development runs on Windows 10 with an NVIDIA GeForce RTX 4070 (12 GB).
- The UI is a local web app with fast previews plus full-resolution runs.
- The project owner directs the work and seldom edits code, so readability and
  automated checks matter more than squeezing out raw speed early.

## Decision

| Area | Choice |
|---|---|
| Simulation core | Python 3.12, managed with `uv`; NumPy reference implementation first |
| GPU (later) | NVIDIA Warp or CuPy, chosen by benchmark when physics models arrive. Both support native Windows CUDA. JAX is ruled out because it has no native Windows GPU support. |
| Previews | The same core code at reduced resolution, so previews and full runs cannot disagree |
| Backend | FastAPI: synchronous previews, plus background jobs for full runs |
| Frontend | TypeScript + React + Vite |
| Run records | `config.toml` + metadata (code version, seed, library versions) + Zarr arrays |
| Validation | pydantic models for every config and registry file |
| Quality | ruff (lint and format), pyright (strict), pytest, pre-commit hooks; ESLint and Vitest for the frontend |
| CI | GitHub Actions on every push and pull request (CPU only; GPU tests run locally) |

## Consequences

- One implementation of each model serves both previews and full runs.
- GPU acceleration is a separate backend behind the same model interface, and it
  is checked against the NumPy reference in tests.
- CI can't exercise GPU code paths, so GPU tests are marked and run locally
  before release.
