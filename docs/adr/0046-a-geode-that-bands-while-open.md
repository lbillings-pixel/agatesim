# 46. A geode that bands while open

- Status: accepted
- Date: 2026-10-17
- Builds on: [ADR 0035](0035-what-the-mechanistic-tier-requires.md), [ADR 0037](0037-mechanistic-quartz-geode.md) (and its amendment)

## Context

The mechanistic quartz-centre geode (ADR 0037) closes its cavity from the
start. Its chalcedony holds only 2–3 bands, because a closed cavity ends H1's
rhythm: the silica falls and the rejected impurity concentrates, and 476
parameter sets tried kept no visible bands (ADR 0037 amendment). The form is
banded chalcedony giving way to quartz, so the amendment proposed a history in
which the cavity is resupplied while the chalcedony bands and closes before
the quartz grows.

## Literature

- Silica reaches volcanic agates by diffusion of monomeric silicic acid
  through the host rock's pore space, since free flow is lacking in most
  rocks; "the continuous supply of silicic acid results in the accumulation of
  silica and the filling of the cavities" ([@goetze2020] §5.3). Silica's low
  solubility means much water must pass to fill a cavity (Landmesser, cited
  there): the cavity is an open system while it fills.
- "The prevailing hypothesis is that voids in volcanic rock are filled in
  cycles, from the rim to the center", by silica-rich fluids entering through
  microfissures or infiltration canals; in Moroccan geodes idiomorphic quartz
  grows at the final stage, in the centre ([@dumanska2013], introduction and
  results).
- Heaney's mechanism: chalcedony grows from a weakly polymerised silica
  solution and leaves an ever more dilute one, undersaturated for amorphous
  silica but saturated for quartz, from which prismatic quartz grows last.
  The authors judge separate entries for the final quartz "not possible"
  ([@moxon2020] §2.4). A quartz centre is the dilute remainder of the last
  fluid, not a new influx.
- No source says when or how a geode's supply ends. Infiltration channels are
  debated: one review reads most as deformation of plastic silica rather than
  supply channels ([@goetze2020] §5.5).

## Decision

1. **`closes_at`** for H1 (`effective`, share of the cavity filled; default
   0 = closed from the start, as before). With a silica inventory, the bulk
   stays at its start (resupplied) until that share of the cavity has filled.
   Then the fluid in the space still open is trapped at the start
   concentrations; its silica can fill a share F\* (`silica_inventory`) of
   that space, and the impurity rejected from then on stays in it. With
   `closes_at = 0` the equations are those of ADR 0037, and results are
   bit-identical.
2. **The closing is a scheduled change of conditions** (ADR 0035 rule 2): it
   sets when the supply ends, not any band's duration, contrast or position.
   Nothing is said about why the supply ends.
3. **Verification preset** `quartz-geode-mechanistic` now closes at 0.6 of the
   cavity, with quartz below 0.8 of the starting silica (was 0.6). With a
   later closing the trapped fluid is smaller and the quartz zone thinner; at
   a threshold of 0.6 the crystals' inward coarsening fails for closings at
   0.6 of the cavity and later (scan below), so the threshold is raised.
   `quartz_below` is an effective parameter: no source gives the
   concentration at which quartz replaces chalcedony.

## Results

- **Bands.** At 768 px the preset grows 12 bands, the last 5.8 mm from the
  wall; closed from the start, the same cavity grows 2, the last 0.6 mm from
  the wall. Chalcedony, quartz and open centre take 78%, 14% and 8% of the
  cavity.
- **Criteria.** It passes at 768, 512, 384 and 256 px: no quartz pixel
  touches the wall, crystals widen inward (Spearman 0.99, 0.87, 0.90, 0.87;
  118 crystals at 768 px, mean width 0.61 → 0.83 mm), and all quartz follows
  the last chalcedony.
- **Scan** (384 px; inventory F\*, quartz threshold, closing share):
  with a threshold of 0.8 or 0.9, all 12 sets with F\* 0.6–0.9 and closings at
  0.5, 0.6 and 0.7 pass (coarsening 0.67–0.99); the band count rises with the
  closing (0.3: 6, 0.5: 10, 0.6: 12, 0.7: 14, 0.8: 16). With the old threshold
  of 0.6, closings at 0.6 and later mostly fail the coarsening test: the
  quartz zone is too thin for crystals to compete.
- **Nothing else changes.** All 24 2D presets hash bit-identical before and
  after the change (the geode preset with `closes_at = 0`).
- **Tests.** Closing late gives at least three times the bands of closing at
  the start, with the front matching the open cavity's until it closes, and
  quartz last; the closed-from-start geode (threshold 0.6) still passes.

## Consequences

- The mechanistic geode shows banded chalcedony, then a clear, unbanded zone
  grown after the closing, then quartz crystals that coarsen inward, with an
  open centre. The banding still stops when the cavity closes, as ADR 0037's
  amendment found; only the resupplied part is banded.
- The geode is no longer "nothing scheduled" (ADR 0037 §4): one change of
  conditions is. The closed-from-start version still passes the criteria
  (a test keeps it), so the earlier finding stands: the transition to quartz
  needs no schedule, the banding does.
- 3D: H1's quartz in 3D still has no crystals; the 3D geode stays procedural
  for now.
