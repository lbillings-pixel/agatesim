# 40. Mechanistic botryoidal, eye, tube and moss agate in 3D

- Status: accepted
- Date: 2026-10-17
- Builds on: [ADR 0021](0021-three-dimensional-runs.md), [ADR 0023](0023-growth-from-nuclei-in-3d.md), [ADR 0025](0025-inclusions-in-3d.md), [ADR 0036](0036-mechanistic-moss.md), [ADR 0038](0038-mechanistic-botryoidal.md), [ADR 0039](0039-mechanistic-eye-and-tube.md)

## Context

ADRs 0036, 0038 and 0039 verified moss, botryoidal, eye and tube agate at the
mechanistic tier in 2D. In 3D, spherulitic H1, filaments under H1, and the
staged model's spherulite and dendrite stages were rejected. The 3D growth
model (ADR 0023, 0025) already keeps its solid exact as simple pieces (wall
offset, balls, bed, filaments, aggregates) and places nucleation sites from a
fixed reference lattice.

## Decision

1. **A module for H1 and the staged model in 3D** (`agatesim.volume.fronts`),
   on the growth model's exact solid (`GrowthSolid`, made public with its site
   placement, spherulite metric and aggregation):
   - H1 lining grows from the nearest solid, wall or filament; spherulitic H1
     takes each point's growth distance from the spherulite that reaches it
     first. Filaments are inclusions, as in the growth model.
   - The staged model's solid after each stage stays exact: a wall stage that
     stops early offsets every piece by its depth; a floor stage adds a bed; a
     spherulite stage that stops early adds balls of radius rate × depth; a
     dendrite stage adds its aggregate (3D aggregation, ADR 0025).
2. **Unchanged results.** H1 against the wall alone runs exactly as before, and
   the staged model's distances reduce to the old formula when no new pieces
   are present: all 12 earlier 3D presets give bit-identical cuts and volumes,
   and all 17 2D presets are unchanged.
3. **Four 3D presets** with the 2D presets' settings: `botryoidal-mechanistic-3d`,
   `eye-mechanistic-3d`, `tube-mechanistic-3d` and `moss-mechanistic-3d`.
4. Still rejected in 3D: H2 walls in the staged model. H1's quartz in 3D has no
   crystals, so the mechanistic geode stays 2D.

## Results

All four pass on their configured cuts. On 100 random cuts (512 px, seed 0,
the protocol of ADRs 0023–0025):

| Form | Mechanistic 3D | Procedural 3D |
|---|---|---|
| Botryoidal | 100% | 98% |
| Eye | 85% | 78% |
| Moss | 100% | 100% |
| Tube | 13% | 11% |

Tube agate's rings show only on cuts within about 30° of square-on to the
filaments, for either model (ADR 0025). On random cuts through the mechanistic
botryoidal preset, bands look a median 0.98 of their true thickness (the
growth distance from a site isn't a wall distance, so the 1.155 of a
wall-parallel band doesn't apply).

## Consequences

- Eight of the nine mechanistic forms now run in 3D; the geode is the exception.
- Tests (`tests/test_volume_fronts.py`): each preset passes its configured cut;
  the spherulite stage fills its share and lining the rest; H1 encloses 3D
  dendrites; filaments get the first H1 bands, the wall's last bands when
  they're absent.
