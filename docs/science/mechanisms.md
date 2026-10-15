# Agate formation: what is known, what is debated, and what it means for the model

> **Status: first draft (2026-10-14).** Each claim is limited by how far its source
> has been read. See the `checked` field in `references/catalogue.toml`. Most
> sources so far have been checked at citation or abstract level, and reading the
> full texts is ongoing work.

## 1. What agate is

Agate is banded **chalcedony**, a microcrystalline form of silica (SiO₂).

- Its layers can be intergrown with quartz, opal, cristobalite or moganite, and
  often contain mineral inclusions and water ([@goetze2020]).
- At the microscopic scale, the visible fibres are built from far smaller quartz
  crystallites, about 8–100 nm long, aligned along particular crystal directions
  ([@lu1994]).
- Chalcedony fibres are elongated along [110] and twist periodically about that
  axis. Heaney's growth model explains this, along with dense Brazil twinning and
  moganite intergrowths, by spiral growth on a screw dislocation from short-chain
  silica polymers ([@heaney1993]).

## 2. Where it forms (our host settings)

- **Volcanic:** gas cavities (vesicles) in lavas, both silica-poor and silica-rich
  (for example basalt and rhyolite). Most agate occurs here, and the silica is
  often thought to come from late- or post-volcanic alteration of the host rock
  ([@goetze2020]).
- **Sedimentary:** nodules formed during diagenesis, the changes a sediment
  undergoes after burial ([@goetze2020]).
- **Seams:** hydrothermal veins and cracks ([@goetze2020]).

## 3. Conditions

- **Temperature:** fluid-inclusion and oxygen-isotope data indicate formation at
  roughly 20–230 °C ([@goetze2020]). For basic igneous hosts, the consensus is
  reported to be below 100 °C ([@moxon2020]). Heaney's review supports
  precipitation from slightly saturated solutions below about 100 °C
  ([@heaney1993]).
- **Chemistry:** elements from the host rock (Al, Ca, Fe, Na, K) are enriched in
  agate, and some agates carry unusually high Ge, B or U ([@goetze2020]). Iron in
  particular controls much of agate's colour.

## 4. How the bands form: competing hypotheses

There is no consensus ([@goetze2020], [@moxon2020]). The simulator treats each
hypothesis as a swappable mechanism (ADR 0003).

| # | Hypothesis | Key idea | Sources | Model family |
|---|---|---|---|---|
| H1 | Self-organized crystallization | Feedback between growth and composition at the crystallization front produces rhythmic bands without any external cycling. Bands alternate between straight-fibred, trace-element-poor layers and twisted-fibred, trace-element-rich layers. | [@wang1990], [@merino1995], [@heaney1995] | Coupled front growth with concentration feedback (oscillatory zoning) |
| H2 | Liesegang-type precipitation–diffusion | Supersaturation builds up, nucleates, then depletes, giving periodic precipitation bands in a gel or porous medium, without sedimentation. | [@krug1993], [@jahnke2008], [@liu2025] | Reaction–diffusion with nucleation thresholds; phase-field (Cahn–Hilliard) separation of the precipitate |
| H3 | Repeated fluid pulses | Each pulse of silica-bearing fluid deposits a layer, so bands record changes in external supply. | Debated in the literature; primary sources to add | Wall-inward deposition driven by a supply schedule |
| H4 | Gravity settling | Particles too large to stay suspended settle to the cavity floor, forming horizontal (Uruguay, waterline) bands. One study finds these bands are made of euhedral quartz grains (0.5–4 µm) and/or spherulites (≤100 µm), deposited after the wall-lining bands and coarse quartz. | [@lu1994] | Particle sedimentation in a still pool |

H1–H3 explain **wall-parallel (fortification)** banding. H4 explains **waterline**
banding. Nature records both orders of the two stages. In a geode, horizontal
Uruguay bands can also form a flat floor that later agate bands drape over
([@lu1994]). The combined archetype therefore takes its stage order from the run's
schedule.

## 5. Optical archetypes

- **Shadow agate:** shadows appear to sweep across the slab as it is tilted, an
  effect tied to alternating translucent and opaque bands. We haven't yet found a
  peer-reviewed optical explanation, so the renderer will start from that
  description and treat the mechanism as an open question.
- **Iris agate:** very fine banding acts as a diffraction grating in thin,
  backlit slices. Reported band densities vary widely between informal sources, so
  a peer-reviewed measurement is still to be found.

## 6. What this means for the simulator

1. **Output fields the formation models must produce:** phase (chalcedony,
   quartz, moganite, opal, void), impurity concentration (an Fe stand-in for
   colour), fibre orientation, crystallite/grain size, porosity, and band index.
2. **Inputs, which can vary over time:**
   - silica concentration and supply schedule
   - temperature
   - pH
   - impurity supply
   - gravity vector
   - nucleation-site density
   - cavity geometry
   - host-rock permeability
3. **First procedural model (M1):** wall-offset banding with angular corners, a
   schedule-driven band spacing and contrast (an H3 analogue), and a horizontal
   fill confined to the cavity floor under gravity (an H4 analogue).
4. **First mechanistic model (later):** a 2D reaction–diffusion and phase-field
   precipitation model along the lines of [@liu2025] (H2), followed by
   front-feedback oscillatory zoning (H1).

## 7. Open questions to resolve by reading the full texts

- Which dimensionless numbers control band spacing in H1 and H2, and what ranges
  do natural agates imply?
- What drives fibre twisting, and should the model represent fibre orientation
  explicitly?
- Is there a quantitative optical model of the shadow effect?
- What are measured iris-band spacings, from peer-reviewed sources?
