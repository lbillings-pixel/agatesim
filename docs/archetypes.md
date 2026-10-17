# Archetype ladder

<!-- Generated from src/agatesim/archetypes/registry.toml by
     `agatesim archetypes --write docs/archetypes.md`. Do not edit by hand. -->

Each archetype is an agate form the simulator aims to reproduce. An archetype is
**verified** for a model tier only when a committed preset using that tier passes
every criterion below in CI (ADR 0005). Criteria without a threshold are
provisional until the archetype is implemented.

| Rung | Archetype | Procedural | Mechanistic | Subsystem | Hosts | Depends on |
|---:|---|---|---|---|---|---|
| 1 | [Fortification (concentric) banding](#fortification) | verified | verified | formation | volcanic, sedimentary | — |
| 2 | [Vein / seam agate](#seam) | verified | verified | formation | seam | fortification |
| 3 | [Waterline (Uruguay-type) horizontal banding](#waterline) | verified | verified | formation | volcanic, sedimentary | — |
| 4 | [Combined fortification and waterline banding](#fortification-waterline) | verified | verified | formation | volcanic, sedimentary | fortification, waterline |
| 5 | [Banded agate with quartz-crystal centre](#quartz-geode) | verified | verified | formation | volcanic, sedimentary | fortification |
| 6 | [Botryoidal habit](#botryoidal) | verified | pending | formation | volcanic, sedimentary, seam | fortification |
| 7 | [Eye agate](#eye) | verified | pending | formation | volcanic, sedimentary | botryoidal |
| 8 | [Tube agate](#tube) | verified | pending | formation | volcanic, sedimentary | eye |
| 9 | [Moss / dendritic agate](#moss) | verified | verified | formation | volcanic, sedimentary, seam | — |
| 10 | [Plume agate](#plume) | verified | pending | formation | volcanic, sedimentary | moss |
| 11 | [Shadow agate](#shadow) | verified | pending | optics | volcanic, sedimentary | fortification |
| 12 | [Iris agate](#iris) | verified | pending | optics | volcanic, sedimentary | fortification, shadow |

## Fortification (concentric) banding

<a id="fortification"></a>

Bands that follow the cavity wall inward, layer after layer, keeping the wall's
corners as sharp angular turns. The basic agate form, and the foundation most
other archetypes build on.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `wall-parallel` | Bands run parallel to the cavity wall. | Mean |cos θ| between band-boundary normals and the distance-to-wall gradient. | value ≥ 0.9 |
| `corners-preserved` | Angular turns in the wall propagate inward as angular turns in the bands. | Worst, over wall corners, of the median turn width / band spacing for bands near the corner. Turn width is the lateral distance over which a band's direction swings through the middle half of its turn at the corner: where the bisector crosses the band, or at the band's own corner within 4 band spacings of it if that is sharper (ADR 0022). Needs bands at least 5 px apart. | value ≤ 0.7 |
| `closed-bands` | Bands form closed loops around the cavity centre. | Fraction of bands (excluding the innermost) that are one connected ring separating inside from outside. | value ≥ 0.9 |
| `band-count` | Enough distinct bands to read as banding. | Number of distinct bands present. | value ≥ 8 |

## Vein / seam agate

<a id="seam"></a>

Banding in an elongated crack, growing inward from both walls toward a central
suture, open void, or quartz infill.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `elongate-host` | The cavity is a high-aspect-ratio crack. | Ratio of the cavity's standard deviations along its long and short axes. | value ≥ 5 |
| `mirror-symmetry` | Band sequences on opposite walls mirror each other about the seam's midline. | Minimum correlation between each cross-section's band profile and its reflection, over 7 sections across the middle half of the seam. | value ≥ 0.8 |
| `central-suture` | Growth fronts from the two walls meet at, or leave open, a central plane. | Worst offset of the last-deposited material (or void) from each cross-section's midpoint, as a fraction of its width. | value ≤ 0.1 |

## Waterline (Uruguay-type) horizontal banding

<a id="waterline"></a>

Flat, parallel bands lying perpendicular to gravity at the cavity floor. They
record which way was "up" at the time they formed (a geopetal indicator).

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `gravity-normal` | Band normals align with the configured gravity vector. | Mean |cos θ| between band-boundary normals and gravity. | value ≥ 0.95 |
| `planar` | Bands are flat, not curved to the wall. | Worst RMS residual of a straight-line fit to any band boundary, as a fraction of cavity size. | value ≤ 0.005 |
| `floor-confined` | Horizontal bands occupy the gravitational bottom of the cavity. | Offset of the banded fill's centroid below the cavity centroid along gravity, as a fraction of cavity size. | value ≥ 0.05 |
| `geopetal-recoverable` | The gravity direction can be recovered from the result alone. | Angle (degrees) between true gravity and 'down' estimated from band orientation and which side the open space is on, without using gravity or deposition order. | value ≤ 3 |

## Combined fortification and waterline banding

<a id="fortification-waterline"></a>

Wall-parallel and horizontal banding in one nodule, produced by changing
conditions over time. The order of the two stages is set by the run's schedule,
since nature records both sequences.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `two-domains` | Distinct wall-parallel and horizontal band domains coexist. | Bands in the smaller domain. A band is horizontal if its boundary is straight (RMS < 0.5% of cavity size) and perpendicular to gravity (mean |cos| > 0.95); wall-parallel if clearly curved (RMS > 1%) and not level overall (mean |cos| < 0.9). | value ≥ 3 |
| `staged` | The domains form in a few uninterrupted stages, not interleaved band by band. | Number of uninterrupted runs of one domain, in deposition order (e.g. wall → horizontal → wall is 3). Whether the stage order matches the schedule is checked in tests. | value ≤ 4 |

## Banded agate with quartz-crystal centre

<a id="quartz-geode"></a>

Chalcedony banding at the rim gives way to coarse, inward-pointing quartz crystals
toward the centre (and sometimes an open void) as silica supply falls.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `phase-transition` | Chalcedony lines the wall and macrocrystalline quartz grows inside it. | Fraction of quartz pixels not touching the host rock (0 if either phase is missing). | value ≥ 0.99 |
| `inward-coarsening` | Crystal size increases toward the centre. | Spearman correlation between depth into the quartz and the mean crystal width along curves of equal wall distance (curve length over crystals crossed), at 10 depths over the outer 80% of the quartz layer (needs at least 8 crystals). Fewer, wider crystals inward survives any cut; ADR 0024. | value ≥ 0.5 |
| `quartz-last` | Quartz formed after the chalcedony banding. | Fraction of quartz deposited no earlier than the last chalcedony. That the transition follows the silica-supply schedule is checked in tests. | value ≥ 0.95 |

## Botryoidal habit

<a id="botryoidal"></a>

Grape-like clusters of hemispherical lobes on the growth surface, formed by
spherulitic growth from many nucleation sites. Bands follow the lobes.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `lobate-front` | The final growth surface is made of rounded lobes. | Fraction of the banding next to the open space whose deposition-time surfaces bulge into it, curving about a centre behind them (radius under 30% of cavity size). Needs open space. | value ≥ 0.6 |
| `lobe-count` | Many lobes, not a single bulge. | Number of distinct growth centres behind the final growth surface (peaks in the density of curvature centres, each holding at least 1% of the surface pixels). That lobe count rises with nucleation density is checked in tests. | value ≥ 5 |
| `bands-follow-lobes` | Internal bands are concentric about the lobes, not parallel to the wall. | Fraction of band-boundary pixels whose band curves about a centre behind it. | value ≥ 0.7 |

## Eye agate

<a id="eye"></a>

Isolated, concentrically banded "eyes": spherulites nucleated at the wall. In a
cross-section they appear as half-ring systems rooted on the wall, overgrown by
later banding; on a surface ground parallel to the wall they appear as circles.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `discrete-eyes` | Several separate band systems radiate from their own centres. | Number of distinct growth centres of the banding (peaks in the density of band-boundary curvature centres, each holding at least 1% of band-boundary pixels). | value ≥ 3 |
| `wall-nucleated` | Eyes are rooted at the cavity wall. | Fraction of growth centres that are eyes rooted at the wall: within 3% of cavity size of the original wall (a cut through the nucleation sites); or off it with no seed nearby and either rings closed around at least 75% of directions (a cut along the wall, showing a bullseye; ADR 0024) or arcs centred within 0.75 of their curvature radius from the wall (a cut through the side of an eye's dome; ADR 0031). Rings around a seed are tubes. | value ≥ 0.8 |
| `isolated-eyes` | The eyes are separate, not a continuous botryoidal crust. | Fraction of the first banding on the wall that is ordinary layering rather than radiating from a centre. | value ≥ 0.3 |

## Tube agate

<a id="tube"></a>

Chalcedony banding grown around thin linear seeds (needles, filaments, stalactitic
channels). In cross-section each tube shows up as a small concentric ring system.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `seed-concentric` | Bands around each seed are circles about it. | Worst seed's fraction of band boundary in its ring zone (out to halfway to the nearest other solid) lying within 10% of that band's median distance from the seed. | value ≥ 0.8 |
| `seed-placement` | Ring systems sit where the seeds are. | Worst seed's offset from the centre of its ring system (median of circle fits to its band boundaries), as a fraction of the ring zone's radius. | value ≤ 0.1 |

## Moss / dendritic agate

<a id="moss"></a>

Branching, tree-like inclusions in translucent chalcedony. Two kinds share the
name: dendrites of Mn or Fe oxides (grown by aggregation of diffusing
particles, or as fingers of infiltrating fluid) and green filamentous fabrics
with Fe-silicate cores wrapped in chalcedony.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `fractal-dimension` | Inclusions are branched, like natural dendrites. | Area-weighted mean box-counting dimension of each inclusion at least 2 mm across, measured on its own between 0.4 mm (or 2 px) and half its extent (a line is 1, a solid patch 2; large DLA clusters approach 1.7, smaller ones measure lower). | 1.3 ≤ value ≤ 1.9 |
| `translucent-matrix` | Dendrites sit in a mostly clear host, not a mass of inclusions. | Share of the cavity occupied by inclusions. | value ≤ 0.2 |

## Plume agate

<a id="plume"></a>

Feathery, upward-billowing inclusions rising from a base and later enclosed by
chalcedony; interpreted as silica-garden self-assembly driven by osmosis,
reaction and buoyancy.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `anisotropic-growth` | Plumes grow upward from their base. | Mean cos² between the local branch direction of the inclusions (structure tensor over 0.4 mm, weighted by coherence) and gravity: 1 = all vertical, about 0.5 = pointing every way. | value ≥ 0.7 |
| `encapsulated` | Plumes are enclosed by later chalcedony. | Share of inclusion pixels with no open space within 2 px. | value ≥ 0.98 |

## Shadow agate

<a id="shadow"></a>

An optical effect: alternating translucent and opaque bands make shadows appear
to sweep across a slab as it is tilted or the light moves. Needs the optical
renderer, not just the formation model.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `alternating-translucency` | The banding alternates between translucent and opaque layers. | Mean change in translucency between consecutive bands, in deposition order (0 = uniform, 1 = strict clear/milky alternation). | value ≥ 0.6 |
| `angle-dependent-shadow` | The rendered shadow pattern moves with the light angle. | How far the shadow inside clear bands (horizontal crossings between milky bands) moves across them, as a fraction of their width, when the light swings between opposite directions (largest swing over ±20° and ±40°); counted only if the shadow is visible (median contrast across the band at least 0.2) and sits on opposite sides for opposite light at every angle. | value ≥ 0.3 |

## Iris agate

<a id="iris"></a>

Rainbow colours in thin, backlit slices, caused by very fine banding acting as a
diffraction grating. Needs wave-optics rendering.

| Criterion | Description | Metric | Pass if |
|---|---|---|---|
| `grating-spacing` | Band spacing is fine enough to diffract visible light. | Median micro-band spacing (µm) where regular micro-banding is visible (pigment < 0.3, translucency > 0.4); reported oscillatory zonation is 0.5–5 µm, iris bands about 2 µm. | 0.5 ≤ value ≤ 5 |
| `spectral-dispersion` | Transmitted light separates into colours at angles the grating equation predicts. | Median difference (nm) between the wavelength of the rendered colour (from its hue) and the first order predicted by d·sin θ = λ, over pixels where that prediction is 450–630 nm, at views of 12°, 16° and 20°. | value ≤ 15 |
