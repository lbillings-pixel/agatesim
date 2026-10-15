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
- GPU: NVIDIA RTX 4070 (12 GB). CI has no GPU.

## Commands
- `uv sync`: install
- `uv run pytest` / `uv run ruff check` / `uv run ruff format` / `uv run pyright`
- `uv run agatesim archetypes --write docs/archetypes.md`: regenerate after
  editing registry.toml

## Rules
- Keep docs/science claims within each source's `checked` level in
  references/catalogue.toml. Cite as `[@id]`, and add new sources to the catalogue.
- Never mark an archetype `verified` without a committed preset that passes its
  criteria in CI. Changing a verified archetype's criteria requires an ADR.
- Label every model parameter `physical` or `effective` (ADR 0003).
- Procedural results are never evidence for a formation mechanism.
- Commits use the no-reply email already set in git config. Never commit secrets
  or personal email addresses. The repo will go public later.
