# 33. Isotropic H2 in 3D, and H2 as a staged wall mechanism

- Status: accepted
- Date: 2026-10-16
- Builds on: [ADR 0020](0020-staged-mechanisms.md), [ADR 0027](0027-liesegang-in-3d.md)

## Context

- In 3D, H2's spots lined up with the lattice axes (ADR 0027). Both the
  six-neighbour Laplacian, whose error favours the axes, and the rule that
  lets precipitate spread only to face neighbours could cause it.
- The staged model (ADR 0020) chains H1 wall stages and H4 floor stages. The
  backlog asked whether H2 could take the wall stages: Liesegang rings, then
  settled layers, or the reverse.

## Decision

1. **A 19-point Laplacian in 3D** (`agatesim._rd.stencil3`, `liesegang3(...,
   isotropic=True)`, now the default): face neighbours weighted 1/3, edge
   neighbours 1/6. Its error is the same in every direction to fourth order
   (Σ w x⁴ = 3 Σ w x²y²), which the six-neighbour stencil fails, and that is the
   negative control in `tests/test_volume_liesegang.py`. Precipitate also
   spreads to edge neighbours. The step stays stable at the same dt (largest
   stencil eigenvalue 16/3 against 12). The six-neighbour stencil stays
   available for comparison; 2D H2 is unchanged.
2. **H2 as a wall mechanism** in the staged model: `wall_mechanism =
   "liesegang"` fills the wall stages with H2. `run_liesegang` takes an open
   `region`; in a later stage the reactant enters through every surface of the
   open space, earlier deposits included (an assumption). Not available in 3D
   (rejected with a message).

## Results

- **Grid alignment.** On a central cut through a round vesicle (40 mm, 0.1 mm
  lattice), the alignment of the precipitate's edges with the lattice axes,
  ⟨|∇p|² cos 4θ⟩ / ⟨|∇p|²⟩, falls from 0.152 to −0.017: from a clear preference
  for the axes to none. By eye, a faint cross arrangement of the spots
  remains, so the artefact is largely, not wholly, removed.
- **3D random cuts of `liesegang-nodule-3d`** (100, 768 px, seed 0, as in
  ADR 0027), with the isotropic stencil:

  | Criterion | Six neighbours (ADR 0027) | 19 points |
  |---|---|---|
  | all four (fortification) | 0% | 0% |
  | wall-parallel | 54% | 91% |
  | closed-bands | 10% | 25% |
  | band-count | 50% | 0% |
  | corners-preserved | 10% (20 judged) | 0% |

  The bands follow the wall far more often, as expected once the spots no
  longer follow the lattice. But there are fewer of them: the configured cut
  shows 5 bands (11 before), all closed (4 of 4) and wall-parallel (0.91), too
  few for the corner test to judge. Letting precipitate spread to edge
  neighbours makes it spread more readily, so bands merge; the preset's
  thresholds were tuned with the old rule. H2 still fails fortification in 3D.
- **H2 then H4 stages** (the combined-form preset with H2 walls, 0.1 mm
  lattice, 768 px):
  - floor then wall: passes the combined form (12 horizontal and 16
    wall-parallel bands; sequence floor → wall). The H2 rings arch over the
    flat floor.
  - wall then floor, and wall-floor-wall: fail two-domains (0 and 1
    wall-parallel bands). The first H2 stage stops at the rim's 30% share,
    and H2's first band forms some way in from the wall, so the rim holds
    almost no separate bands.

## Consequences

- 3D H2 results before this ADR (ADR 0027) were made with the six-neighbour
  stencil; the survey above replaces its numbers. The gallery's 3D H2 image
  (docs/images/volume.png) predates the change.
- Backlog: re-tune the 3D H2 preset's spreading and nucleation thresholds for
  the 19-point rule, to restore the band count; the 2D H2 has the same kind of
  four-neighbour bias.
- H2 can now be staged with settled layers, as one possible history of the
  combined form. Whether a real agate's rings could form after its floor
  layers is a question for the literature.
