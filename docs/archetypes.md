# Archetype ladder

<!-- Generated from src/agatesim/archetypes/registry.toml by
     `agatesim archetypes --write docs/archetypes.md`. Do not edit by hand. -->

Each archetype is an agate form the simulator aims to reproduce. An archetype is
**verified** only when every criterion below passes against a simulation run.
Metrics are provisional until the archetype is implemented.

| Rung | Archetype | Status | Subsystem | Hosts | Depends on |
|---:|---|---|---|---|---|
| 1 | [Fortification (concentric) banding](#fortification) | pending | formation | volcanic, sedimentary | — |
| 2 | [Vein / seam agate](#seam) | pending | formation | seam | fortification |
| 3 | [Waterline (Uruguay-type) horizontal banding](#waterline) | pending | formation | volcanic, sedimentary | — |
| 4 | [Combined fortification and waterline banding](#fortification-waterline) | pending | formation | volcanic, sedimentary | fortification, waterline |
| 5 | [Banded agate with quartz-crystal centre](#quartz-geode) | pending | formation | volcanic, sedimentary | fortification |
| 6 | [Botryoidal habit](#botryoidal) | pending | formation | volcanic, sedimentary, seam | fortification |
| 7 | [Eye agate](#eye) | pending | formation | volcanic, sedimentary | botryoidal |
| 8 | [Tube agate](#tube) | pending | formation | volcanic, sedimentary | eye |
| 9 | [Moss / dendritic agate](#moss) | pending | formation | volcanic, sedimentary, seam | — |
| 10 | [Plume agate](#plume) | pending | formation | volcanic, sedimentary | moss |
| 11 | [Shadow agate](#shadow) | pending | optics | volcanic, sedimentary | fortification |
| 12 | [Iris agate](#iris) | pending | optics | volcanic, sedimentary | fortification, shadow |

## Fortification (concentric) banding

<a id="fortification"></a>

Bands that follow the cavity wall inward, layer after layer, keeping the wall's
corners as sharp angular turns. The basic agate form, and the foundation most
other archetypes build on.

| Criterion | Description | Provisional metric |
|---|---|---|
| `wall-parallel` | Bands run parallel to the cavity wall. | Mean |cos θ| between band-contour normals and the distance-to-wall gradient ≥ threshold. |
| `corners-preserved` | Angular turns in the wall propagate inward as angular turns in the bands. | Curvature peaks of inner bands align with wall corners within an angular tolerance. |
| `closed-bands` | Bands form closed loops around the cavity centre. | Fraction of band contours that are closed ≥ threshold. |
| `band-count` | Enough distinct bands to read as banding. | Band count from a wall-to-centre profile within a configured range. |

## Vein / seam agate

<a id="seam"></a>

Banding in an elongated crack, growing inward from both walls toward a central
suture, open void, or quartz infill.

| Criterion | Description | Provisional metric |
|---|---|---|
| `elongate-host` | The cavity is a high-aspect-ratio crack. | Cavity aspect ratio ≥ threshold. |
| `mirror-symmetry` | Band sequences on opposite walls mirror each other about the seam's midline. | Correlation between reflected wall-normal profiles ≥ threshold. |
| `central-suture` | Growth fronts from the two walls meet at, or leave open, a central plane. | Locus of final growth lies within a tolerance of the medial axis. |

## Waterline (Uruguay-type) horizontal banding

<a id="waterline"></a>

Flat, parallel bands lying perpendicular to gravity at the cavity floor. They
record which way was "up" at the time they formed (a geopetal indicator).

| Criterion | Description | Provisional metric |
|---|---|---|
| `gravity-normal` | Band normals align with the configured gravity vector. | Mean |cos θ| between band normals and gravity ≥ threshold. |
| `planar` | Bands are flat, not curved to the wall. | RMS residual of a straight-line fit to each band ≤ threshold. |
| `floor-confined` | Horizontal bands occupy the gravitational bottom of the cavity. | Centroid of horizontal-band area lies below the cavity centroid along gravity. |
| `geopetal-recoverable` | The gravity direction can be recovered from the result alone. | Gravity direction estimated from the bands matches the configured value within tolerance. |

## Combined fortification and waterline banding

<a id="fortification-waterline"></a>

Wall-parallel and horizontal banding in one nodule, produced by changing
conditions over time. The order of the two stages is set by the run's schedule,
since nature records both sequences.

| Criterion | Description | Provisional metric |
|---|---|---|
| `two-domains` | Distinct wall-parallel and horizontal band domains coexist. | Both the fortification and waterline orientation criteria pass within their own domains. |
| `sequence-honoured` | The cross-cutting relationship matches the configured stage order. | The later domain's bands truncate or drape over the earlier domain's, as scheduled. |

## Banded agate with quartz-crystal centre

<a id="quartz-geode"></a>

Chalcedony banding at the rim gives way to coarse, inward-pointing quartz crystals
toward the centre (and sometimes an open void) as silica supply falls.

| Criterion | Description | Provisional metric |
|---|---|---|
| `phase-transition` | Microcrystalline banding gives way to macrocrystalline quartz inward. | Phase field switches from chalcedony to quartz along wall-to-centre profiles. |
| `inward-coarsening` | Crystal size increases toward the centre. | Grain size increases monotonically with distance from the wall in the quartz zone. |
| `supply-controlled` | The transition responds to the silica-supply schedule. | Moving the supply drop in time moves the transition depth in the same direction. |

## Botryoidal habit

<a id="botryoidal"></a>

Grape-like clusters of hemispherical lobes on the growth surface, formed by
spherulitic growth from many nucleation sites. Bands follow the lobes.

| Criterion | Description | Provisional metric |
|---|---|---|
| `lobate-front` | The final growth surface is made of rounded lobes. | Front curvature is mostly positive, with lobe radii in a configured range. |
| `bands-follow-lobes` | Internal bands are concentric about lobe centres. | Band contours fit circles about nucleation sites with residual ≤ threshold. |
| `nucleation-controlled` | Nucleation density controls lobe size. | Mean lobe radius decreases as nucleation-site density increases. |

## Eye agate

<a id="eye"></a>

Isolated, circular, concentrically banded "eyes": spherulites nucleated at the
wall, seen on a cut or weathered surface.

| Criterion | Description | Provisional metric |
|---|---|---|
| `discrete-eyes` | Separate circular band systems are present. | Count of concentric systems within a configured range, each with circularity ≥ threshold. |
| `wall-nucleated` | Eyes are rooted at the cavity wall. | Each eye's centre lies within a tolerance of the original wall. |

## Tube agate

<a id="tube"></a>

Chalcedony banding grown around thin linear seeds (needles, filaments, stalactitic
channels). In cross-section each tube shows up as a small concentric ring system.

| Criterion | Description | Provisional metric |
|---|---|---|
| `seed-concentric` | Bands are concentric about the configured seeds. | Band contours around each seed fit circles with residual ≤ threshold. |
| `seed-placement` | Ring systems sit where the seeds were placed. | Ring-system centres match seed positions within tolerance. |

## Moss / dendritic agate

<a id="moss"></a>

Branching, tree-like inclusions of iron or manganese oxides in translucent
chalcedony, grown by diffusion-limited branching.

| Criterion | Description | Provisional metric |
|---|---|---|
| `fractal-dimension` | Inclusions are branched, like natural dendrites. | Box-counting dimension of the inclusion mask in a configured range (DLA ≈ 1.7 in 2D). |
| `translucent-matrix` | Dendrites sit in a mostly translucent host. | Inclusion area fraction ≤ threshold. |

## Plume agate

<a id="plume"></a>

Feathery, upward-billowing oxide inclusions rising from a base, later enclosed by
chalcedony.

| Criterion | Description | Provisional metric |
|---|---|---|
| `anisotropic-growth` | Plumes grow preferentially in one direction from a base. | Principal-axis anisotropy of each plume mask ≥ threshold. |
| `encapsulated` | Plumes are enclosed by later chalcedony. | Every plume pixel is surrounded by chalcedony phase within a buffer distance. |

## Shadow agate

<a id="shadow"></a>

An optical effect: alternating translucent and opaque bands make shadows appear
to sweep across a slab as it is tilted or the light moves. Needs the optical
renderer, not just the formation model.

| Criterion | Description | Provisional metric |
|---|---|---|
| `alternating-translucency` | The banding alternates between translucent and opaque layers. | Translucency profile across the bands shows alternation contrast ≥ threshold. |
| `angle-dependent-shadow` | The rendered shadow pattern moves with light or view angle. | Displacement of the rendered shadow pattern correlates with angle change (|r| ≥ threshold). |

## Iris agate

<a id="iris"></a>

Rainbow colours in thin, backlit slices, caused by very fine banding acting as a
diffraction grating. Needs wave-optics rendering.

| Criterion | Description | Provisional metric |
|---|---|---|
| `grating-spacing` | Band spacing is fine enough to diffract visible light. | Band spacing in a configured micrometre-scale range. |
| `spectral-dispersion` | Transmitted light separates into colours at angles the grating equation predicts. | Rendered diffraction angles match d·sin θ = mλ within tolerance. |
