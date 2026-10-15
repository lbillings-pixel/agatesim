# 4. Archetype ladder and verification

- Status: accepted
- Date: 2026-10-14

## Context

"Replicates waterline banding" is meaningless unless it can be checked. Without
quantitative criteria, progress can't be measured and regressions go unnoticed.

## Decision

- **The registry.** `src/agatesim/archetypes/registry.toml` is the single source of
  truth for the targeted forms. Each one has a rung, dependencies, host settings,
  a subsystem (formation or optics), and a list of quantitative criteria.
- **Catalogue first.** All targeted forms are catalogued from the start, including
  ones that won't be implemented for a long time, and begin as `pending`.
  Implementation follows the dependency order.
- **What "verified" means.** An archetype is `verified` only when a committed
  preset (a run configuration) passes every criterion in CI. A verified
  archetype's dependencies must also be verified. The registry loader enforces
  this.
- **Provisional metrics.** Criteria metrics stay provisional until implementation,
  when they gain numeric thresholds.
- **Changing criteria.** Altering a verified archetype's criteria requires a new
  ADR, so criteria can't be quietly loosened to make a test pass.
- **Generated docs.** `docs/archetypes.md` is generated from the registry, and CI
  fails if the two disagree.

## Consequences

- The README can show an honest list of which forms the simulator reproduces now.
- Each new model is judged against fixed, written-down targets.
