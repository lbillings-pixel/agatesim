# Agate formation: what is known, what is debated, and what it means for the model

> **Status: second draft (2026-10-15).** Each claim is limited by how far its
> source has been read. See the `checked` field in `references/catalogue.toml`
> (`sections` means only the listed sections). The two open-access reviews
> ([@goetze2020], [@moxon2020]) and one dendrite study ([@hou2023]) are now read
> in full or in large part; most other sources are still at citation or abstract
> level.

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

What the reviews agree on:

- **Agate starts from non-crystalline silica.** Silicic acid accumulates and
  condenses into silica sols and amorphous silica, the precursors of the agate
  microstructure. High defect densities point to rapid crystallisation under
  non-equilibrium conditions ([@goetze2020] §6). Agate then matures over
  geological time as moganite slowly converts to quartz and crystallites coarsen
  ([@moxon2020] §5).
- **Growth starts at the wall as spherulites.** Crystallisation mostly begins at
  the cavity wall with granular or spherulitic chalcedony, which continues inward
  into fibrous chalcedony. Many agates show three zones: a spherulitic or
  granular rim, fibrous chalcedony, and a macrocrystalline quartz centre
  ([@goetze2020] §4.1.2, §5.4).
- **Visible bands are bundles of finer ones.** A visible band can hold up to 1000
  micro-bands per millimetre. Bands differ in silica phase, crystallite size,
  porosity and finely dispersed pigments such as iron oxides ([@goetze2020]
  §4.1.2). Iron is rejected by the crystallising quartz and carried along the
  front, so it collects along the banding ([@goetze2020] §5.4).
- **Liesegang diffusion in a gel is out of favour as the cause of banding.** Gel
  experiments do reproduce agate-like patterns, but the reviews find colour
  banding is governed mainly by self-organisation of the crystallising silica
  ([@goetze2020] §5.4), and there is "little support" now for metal-ion
  diffusion into a pre-existing gel ([@moxon2020] §5). H2 stays in the table as a
  hypothesis to test, not a favoured one.

| # | Hypothesis | Key idea | Sources | Model family |
|---|---|---|---|---|
| H1 | Self-organized crystallization | Feedback between growth and composition at the crystallization front produces rhythmic bands without any external cycling. Bands alternate between straight-fibred, trace-element-poor layers and twisted-fibred, trace-element-rich layers. | [@wang1990], [@merino1995], [@heaney1995] | Coupled front growth with concentration feedback (oscillatory zoning) |
| H2 | Liesegang-type precipitation–diffusion | Supersaturation builds up, nucleates, then depletes, giving periodic precipitation bands in a gel or porous medium, without sedimentation. | [@krug1994], [@jahnke2008], [@liu2025] | Reaction–diffusion with nucleation thresholds; phase-field (Cahn–Hilliard) separation of the precipitate |
| H3 | Repeated fluid pulses | Each pulse of silica-bearing fluid deposits a layer, so bands record changes in external supply. | Debated in the literature; primary sources to add | Wall-inward deposition driven by a supply schedule |
| H4 | Gravity settling | Particles too large to stay suspended settle to the cavity floor, forming horizontal (Uruguay, waterline) bands. One study finds these bands are made of euhedral quartz grains (0.5–4 µm) and/or spherulites (≤100 µm), deposited after the wall-lining bands and coarse quartz. | [@lu1994] | Particle sedimentation in a still pool |

H1–H3 explain **wall-parallel (fortification)** banding. H4 explains **waterline**
banding. Nature records both orders of the two stages. In a geode, horizontal
Uruguay bands can also form a flat floor that later agate bands drape over
([@lu1994]). The combined archetype therefore takes its stage order from the run's
schedule. One review attributes horizontal layers to gravitational sedimentation
of sols with flocculated silica particles, which needs a high silica
concentration, so horizontally layered agates are typical of particular
localities ([@goetze2020] §4.1.2).

## 5. Forms that grow from points

- **Botryoidal and eye agate.** Agate growth commonly starts as separate
  spherulites at the wall that merge into continuous fibrous layers
  ([@goetze2020] §5.4, Fig. 29), which is the eye-then-layers sequence of the
  eye preset. Colloform or botryoidal textures are read as precipitation of
  silica gel in free space ([@goetze2020] §4.1.2). Spherulites in general
  (reviewed in [@shtukenberg2012], not yet read) have a phase-field model in
  which growth-front nucleation randomises crystal orientation
  ([@granasy2005], abstract only): a candidate mechanistic model.
- **Tube agate.** One review interprets most so-called infiltration channels
  ("escape tubes") as deformation of still-plastic silica rather than supply
  channels ([@goetze2020] §5.5). Pseudo-stalactites in basalt cavities are
  filaments up to 100 cm long with constant diameter, wrapped in concentric
  layers: Fe-rich phases such as celadonite and smectite, then zeolites, then
  silica. Fungal chitin was found in some filament cores ([@goetze2020b]). The
  tube model's geometry (a filament core wrapped by concentric chalcedony)
  matches that description. Nothing in the model depends on what the filaments
  are.
- **Coarse quartz** crystallises "when the SiO2 concentration in the mineralizing
  fluid is low" ([@goetze2020] §6), with a drop in impurities and defects at the
  chalcedony–quartz interface (§5.4). Heaney's mechanism, as summarised in
  [@moxon2020]: a weakly polymerised silica solution forms chalcedony and leaves
  dilute monomeric silicic acid, undersaturated for amorphous silica but
  saturated for quartz, from which prismatic quartz grows last. This supports
  the model's quartz threshold on silica supply (see §7). In the model the
  crystals coarsen inward by geometric selection, the principle usually credited
  to van der Drift ([@vanderdrift1967], citation level only). Whether agate
  quartz does so is still to check.

The procedural model shows a geometric point worth checking against specimens. A
crust of equally fast spherulites much thicker than their spacing grows towards a
smooth layer, the envelope of their growth fronts. Large lobes on a thick crust
therefore need either sparse nucleation or competition between unequal growth
rates (ADR 0008).

## 6. Inclusions: dendrites, moss and plumes

"Moss agate" covers at least two different things, and the literature gives each
its own mechanism.

- **Dendrites of manganese or iron oxide** (dendritic agate). Mineral dendrites
  form where Fe- or Mn-bearing solutions meet oxygen. Chopard and co-authors
  modelled them as a lattice reaction–diffusion process whose conditions set the
  fractal dimension ([@chopard1991], abstract). A study of 3D Mn dendrites found
  growth by attachment of oxide nanoparticles that diffuse to the dendrites,
  "more in line with" diffusion-limited aggregation (DLA) than with the
  competing model of solidified fingers of infiltrating fluid ([@hou2023],
  [@garciaruiz1994]). In that study dendrites competed for particles, so fewer
  and wider dendrites reached farther from their base, and a finite particle
  concentration made the pattern bulkier and not fully scale-free. Particles
  reached dendrite tips first, and banding inside the dendrites records discrete
  fluid pulses. Dendrites usually grow on fracture surfaces, but can also grow
  inside silica gel ([@monecke2023], citation only), and dendrites appear in
  silica-gel experiments at high supersaturation ([@moxon2020] §2.4).
- **Green filaments** (moss agate in the narrow sense). In Deccan basalt cavities,
  filaments with green Fe-silicate cores, randomly intergrown and embedded in
  chalcedony, are compared to moss agate. Each filament has a chalcedony crust up
  to 1 cm thick, and some filaments on ceilings and walls hang downward under
  gravity ([@goetze2020b]). Biosignatures are reported in such fabrics
  ([@goetze2020] §5.5, [@goetze2020b]).
- **Plumes** are interpreted as silica gardens: plant-like structures formed by
  inorganic self-assembly through osmosis, chemical reaction and buoyancy
  ([@goetze2020] §5.5, citing [@haudin2014]). Buoyancy gives them a preferred
  direction, upward.

For M5 the simulator grows inclusions by multi-particle DLA (ADR 0009):
particles start spread through the open space, diffuse, and attach to branches
rooted on the growth surface. Chalcedony then grows over the inclusions, as it
grows over tube filaments. An upward attachment bias (particles stick more
readily to the tops of branches) is a procedural stand-in for the buoyant,
upward-directed growth of plumes. The
alternatives stay open: dendrites growing in fractures or gel after the
chalcedony, and viscous fingering.

## 7. Optical archetypes

- **Shadow agate:** shadows appear to sweep across the slab as it is tilted, an
  effect tied to alternating translucent and opaque bands. A second search (M6)
  again found no peer-reviewed optical study. The M6 renderer therefore tests one
  hypothesis (ADR 0010): light entering a clear band reaches the milky band
  beside it at depth, so the shadow inside each clear band moves to the other
  side when the light does. It is a single-scattering model of a slab whose bands
  run straight down. Its scattering and absorption coefficients are effective
  values, not measurements.
- **Iris agate:** micro-banding acts as a diffraction grating. A review reports
  oscillatory micro-zonation of defects at 0.5–5 µm, with refractive-index
  changes along these bands giving the iris colours, and an iris band spacing of
  about 2 µm ([@cartwright2026] §5.1.1, after [@jones1952]). Iris zones "exist in
  nearly every agate, although they are often concealed by pigmentation"
  ([@cartwright2026] §5.1.1). Another review reports up to 1000 micro-bands per
  millimetre ([@goetze2020] §4.1.2). Non-peer-reviewed sources give figures
  ranging from about 0.1 to 25 µm, so the simulator uses the peer-reviewed range.
  The renderer applies the grating equation (d·sin θ = mλ) with the grating
  lines along the visible bands. The refractive index of chalcedony (1.54) is an
  assumed typical value, still to source.
- **Against two banding hypotheses** ([@cartwright2026] §5.1.1): Liesegang
  patterns lack agate's sharp corners, have ring defects agates don't, and follow
  a spacing law agates don't. External-rhythm models predict that nearby agates
  share band sequences, which they don't. The corner criterion of the
  fortification form and a future check for uncorrelated sequences between
  neighbouring nodules can test mechanistic models against these.
- **Band colours** that the M6 renderer should reproduce: white bands are
  plate-edge structures that reflect light, clear bands are globular and porous,
  and blue comes from Tyndall scattering by the micro-particles ([@goetze2020]
  §5.4).

## 8. What this means for the simulator

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
3. **First procedural models (M1):** wall-offset banding with angular corners, and
   a horizontal fill confined to the cavity floor under gravity (an H4 analogue).
   **M3 adds formation history** (ADR 0007): scheduled silica supply, settling and
   iron. Wall-lining and settling stages can come in either order, matching both
   sequences in [@lu1994]. Below a silica-supply threshold, coarse quartz crystals
   grow inward. Both reviews support this: quartz crystallises from low silica
   concentrations, after chalcedony has used up the polymerised silica
   ([@goetze2020] §6, [@moxon2020] §2.4; see §5). The threshold itself has no
   measured value, so it stays labelled *effective*.
   **M4 adds nucleation** (ADR 0008): a scheduled spherulitic mode in which
   growth radiates from blue-noise sites on the growth surface (botryoidal and
   eye forms), tubes as growth surfaces inside the cavity, and quartz crystals
   with pointed, elongated growth forms that coarsen by geometric selection.
   **M5 adds inclusions** (ADR 0009): branched inclusions grown by multi-particle
   DLA from the growth surface, optionally drifting with gravity for plumes,
   then enclosed by chalcedony.
4. **First mechanistic model (M8, ADR 0013): front feedback (H1).** A generic
   model of the H1 family in the boundary-layer approximation that Wang and
   Merino introduced for zoned crystals ([@kalischewski2006]). Silica is
   consumed at the front and slowly resupplied. An impurity is rejected by the
   front and, once gathered, speeds up crystallisation, as Al³⁺ is proposed to
   ([@cartwright2026] §5.1.1). Bands then self-organise as a limit cycle,
   alternating impurity-rich fast growth with impurity-poor slow growth. The
   model verifies fortification and seam at the mechanistic tier. Two findings
   to test against nature:
   - The oscillation needs switch-like (cooperative) catalysis and slow silica
     resupply. Oscillations are rare at Hill exponent 2 and about 60 times more
     common at 4.
   - In a closed cavity, rejected impurity builds up and ends the oscillation
     within a band or two. Agate trace-element profiles do show a gradual
     accumulation trend ([@halden2000], abstract), so either the system was
     open or the real feedback tolerates the build-up.

   Next: a 2D reaction–diffusion and nucleation model (H2) along the lines of
   [@liu2025] and the pre-nucleation models of [@cartwright2026] §4.1.5.

## 9. Open questions to resolve by reading the full texts

- Which dimensionless numbers control band spacing in H1 and H2, and what ranges
  do natural agates imply? In our H1 model, band spacing is set by the
  boundary-layer thickness δ times the cycle length (about 600 δ at the
  defaults). What is δ in a silica gel or sol?
- Does impurity-catalysed crystallisation in silica actually behave
  cooperatively (switch-like), as our H1 model needs to oscillate?
- What drives fibre twisting, and should the model represent fibre orientation
  explicitly?
- Is there a quantitative optical model of the shadow effect?
- What are measured iris-band spacings, from peer-reviewed sources?
- ~~What controls the switch from chalcedony to macrocrystalline quartz?~~
  Both reviews: low silica concentration once the polymerised silica is used up
  (§5). Still open: is there a measurable concentration, and how do temperature
  and impurities shift it?
- What sets spherulite nucleation density and lobe size in botryoidal
  chalcedony, and do natural lobes coarsen by competition as the model's do?
- Are tube-agate filaments mostly biogenic templates (as reported for Deccan
  pseudo-stalactites) or mineral needles, and does it change the banding around
  them?
- Does quartz in agate geodes show the orientation selection and inward widening
  predicted by geometric selection?
- In dendritic agate, do the dendrites grow in the silica before it crystallises
  (in a gel), or later along fractures? What fractal dimensions are measured on
  agate dendrites specifically?
- Plumes as silica gardens: what sets their width and how upright they are?
