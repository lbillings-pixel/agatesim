# agatesim: notes for Claude

## Working with the owner
- The owner directs and decides. They rarely edit code themselves. Be proactive:
  raise risks, suggestions and next steps, and check in at each milestone
  (see docs/roadmap.md).
- Ask before hard-to-reverse choices (stack, model architecture, archetype
  criteria). Record them as ADRs in docs/adr/.

## Environment (Windows 10, PowerShell 5.1)
- Tools: uv (Python 3.12), Node.js LTS, git, gh. If they aren't on PATH in a
  session, refresh it first:
  `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`
- GPU: NVIDIA RTX 4070 (12 GB). CI has no GPU. `uv sync --extra gpu` installs CuPy
  (cupy-cuda13x with CUDA from PyPI). The reaction–diffusion solver (`agatesim._rd`)
  uses the GPU whenever CuPy finds one (`AGATESIM_GPU=0` declines it, ADR 0054);
  results match NumPy to rounding.

## Commands
- `uv sync`: install (`uv sync --extra gpu` with CuPy). Once the GPU extra is
  installed, run everything as `uv run --no-sync ...`: a plain `uv run` re-syncs
  and removes CuPy, even under a running job.
- `uv run pytest` / `uv run ruff check` / `uv run ruff format` / `uv run pyright`
- `uv run agatesim run <preset|config.toml> [--preview] [--check]`
- `uv run agatesim volume run|survey <3d-preset>`: 3D runs (ADR 0021). Write 3D
  runs under the repo's `runs/`: deep paths (the scratchpad) exceed Windows'
  path limit inside fields.zarr
- `uv run agatesim archetypes --write docs/archetypes.md`: regenerate after
  editing registry.toml
- `uv run python scripts/make_gallery.py`: regenerate docs/images after model or
  render changes
- Web UI: `npm --prefix web run lint|typecheck|test|build`. Build output goes to
  src/agatesim/server/static (gitignored). `uv run agatesim serve` serves it.
  For browser checks, serve on a spare port (`--port 8765 --no-browser`) in the
  background, and stop it afterwards.
- The UI reads model parameters from each model's JSON schema (units and nature
  extras), so new model parameters appear in the UI automatically.
- Commit messages: write to a file in the scratchpad and use `git commit -F`.
  PowerShell 5.1 mangles here-strings passed to native commands.

## Rules
- Keep docs/science claims within each source's `checked` level in
  references/catalogue.toml. Cite as `[@id]`, and add new sources to the catalogue.
- Never mark an archetype `verified` without a committed preset that passes its
  criteria in CI. Status is per tier (procedural / mechanistic). Changing a
  verified archetype's criteria or thresholds requires an ADR.
- Every new criterion needs a negative control in tests/test_criteria.py: a
  result lacking the form that the criterion must reject.
- Models read only the Domain and write only Fields. Criteria read only Fields
  (plus geometry), never model internals.
- Anything random must be resolution-independent (spawned RNG streams; noise in
  world coordinates), so previews match full runs.
- Label every model parameter `physical` or `effective` (ADR 0003).
- Long work reports through `agatesim.progress` (ADR 0054), so the app can show
  the time left and cancel it. Work on lattices of millions of cells in chunks
  (never every cell's coordinates at once), build search trees once, and hand
  GPU memory back after large runs (`_rd.release_gpu_memory`): each has caused
  gigabytes of waste or a crash before. A GPU path must give the CPU path's
  result (hashed draws for anything random, ADR 0057).
- Procedural results are never evidence for a formation mechanism.
- The owner's specimen photos live in `specimens/` (gitignored) and never enter
  the repository, a commit, an artifact or any external service. Anything derived
  from them is written without metadata (they carry GPS). Tests use synthetic
  photos (`agatesim.specimen.synthetic`).
- Commits use the no-reply email already set in git config. Never commit secrets
  or personal email addresses. The repo is public (github.com/lbillings-pixel/agatesim);
  `tests/test_privacy.py` guards images and `specimens/`.
- Commit messages carry no `Claude-Session:` link (owner decision, 2026-10-18;
  history rewritten to remove them). Keep the `Co-Authored-By:` line.
