# 69. Calibration without a ruler: band shape from the reference library (M34)

- Status: accepted (M34, stage 5 of [ADR 0063](0063-specimen-work-restarted-in-stages.md))
- Date: 2026-10-24
- Builds on: [ADR 0064](0064-a-photo-quality-gate.md), [ADR 0065](0065-photo-resolution-in-mm.md), [ADR 0066](0066-reference-library-and-labelling.md), [ADR 0068](0068-feature-maps-from-tags.md)

## Context

Stage 5 tunes the models against photos that pass the quality gate. The gate's
calibration level judges resolution in mm and so needs a ruler (ADR 0065). Only
the owner's three ruler photos have one, and all three are borderline. None of
the 300 reference-library photos carry a scale.

The owner chose calibration **without a ruler** (2026-10-24): statistics that
don't depend on size, measured on the library, and no new photos needed.

Without the scale checks, the calibration limits pass 59 of the 226 usable
library photos where a face is found, and 144 with borderline included. The
most common failure is "bands" (45 photos), then clipped highlights (30), band
contrast (14), JPEG blocking (11) and sharpness (5). Scoring all of them took
304 s and 0.25 GB.

A literature pass (2026-10-24) looked for published measurements of these
statistics:

- **Bands thicken towards the centre.** In 28 band sequences on 13 slices of
  white-striped volcanic agate, measured on greyscale photos, band width "is not
  constant", with the fastest changes near the rim. The fits match bands of
  equal volume on concentric shells (width ∝ r⁻²) [@goldbaum2019]. The paper's
  stated fit quality (R² > 0.995 for all) disagrees with its own table
  (0.9765–0.9993), so it is used as a direction, not as a number to match.
- **Profile roughness.** Greyscale profiles across agate bands are self-affine
  over about two decades, with Hurst exponents 0.36 ± 0.05 and 0.49 ± 0.05
  [@holten1998]. Read at abstract level only: how the profiles were taken
  isn't known.
- **Spacing ratio.** In chemical Liesegang systems, successive band positions
  grow by a factor 1 + p with p from 0.05 to 0.4 [@jahnke2008]. This is not
  agate, and Cartwright et al. find the spacing law isn't seen in agate
  [@cartwright2026]. Recorded for comparison, not as a target.
- **No published numbers** were found for the spread of band thickness within a
  stack, band counts, contrast, or the share of the face taken by the quartz
  core. For these, the library itself is the reference.

## Decision

### 1. A "calibration (no ruler)" level in the quality gate

A third use, `shape`, takes the calibration limits without the resolution and
scale checks. Its badge says that it judges band shape only, and that sizes in
mm still need a ruler. Fit and borderline photos are both used, and results
are reported for each group separately.

### 2. Statistics without a scale

The same code measures a photo and a simulated cut, on band profiles taken
across the bands (the quality gate's profiles), with every length divided by
the face's own size or by the median band spacing:

| Statistic | What it is | Published guide |
|---|---|---|
| Thickness spread | coefficient of variation of band widths along each profile | none |
| Rim-to-centre trend | slope of log band width against depth into the face (depth from the rim divided by the face's inner radius) | positive, faster near the rim [@goldbaum2019] |
| Roughness | Hurst exponent of the grey profile, over windows of two to ten band spacings (amended in step 2, below) | 0.36–0.49 [@holten1998] |
| Spacing ratio | median ratio of successive band widths | Liesegang only [@jahnke2008] |
| Quartz core share | share of the face in the quartz-core map (photos) or the quartz field (simulations) | none |

Each statistic gets a negative control in tests: a synthetic photo built without
the property (even bands, no trend, a smooth profile) that it must report as
absent.

### 3. Simulations blurred like photos

A photo can't show bands thinner than its edge width. The ratio of edge width
to band spacing has no units, so the simulations are blurred until that ratio
matches the photos' range (the quality gate already measures it). Simulations
are measured on random cuts, as photos are of slabs cut wherever they were cut:
oblique and off-centre cuts change the apparent widths and trend
[@goldbaum2019].

### 4. What is calibrated

For each model, the statistics of random cuts across its Randomize ranges are
compared with the library's spread. The report shows where a model's results
fall outside the photos' range and which settings push them there. The owner
decides which **Randomize ranges and defaults** move. Archetype criteria and
thresholds don't change here.

## Consequences

- No new photos, downloads or dependencies. Library measurements are cached
  beside the maps cache (gitignored), as scoring takes about 5 minutes.
- Calibrated ranges match the look of real agates. For procedural models this
  says nothing about formation (ADR 0005). For mechanistic models, a match is
  a precondition for M35's fidelity tests, not evidence of the mechanism.
- Sizes in mm stay uncalibrated until there are photos with a ruler and a
  resolution of 0.2 mm or better (ADR 0065).
- The library is mostly polished, backlit or wetted slabs from collectors. Its
  spread reflects what people photograph, not every agate.
- The quartz core share on photos comes from the M33 map (score 0.91 on the
  owner's taps, centre 0.70), so it is rougher than the other statistics.

## Amendment: step 2 (2026-10-24)

- **Roughness windows start at two band spacings, not one.** A band spacing
  is one band (turn to turn), half a light-and-dark period. On perfectly even
  synthetic bands, windows from one spacing gave H = 0.45, inside the published
  agate range, because the spread jumps when a window first holds a light and a
  dark band. From two spacings, even bands give H = 0.09, and 200 independent random walks
  0.50-0.53 (five seeds).
- **H also rises with the trend.** Smooth bands that thicken inward give H of
  about 0.5 with no roughness at all. H is compared between photos and
  simulations measured alike; it is not read as roughness alone, nor matched to
  [@holten1998].
- **Thickness spread reads low**: 0.18 on synthetic bands whose true spread is
  0.29 (the thinnest blur, and a profile holds about a dozen bands). Photos and
  simulations share the bias.
- Code: `specimen/shape.py` (statistics), `shapes.py` and
  `agatesim library shape` (the library, cached in
  `references/models/shapes.json`), the `shape` use in `specimen/quality.py`.
- **The library** (230 usable photos; 312 s, under 0.62 GB, cached after):
  59 fit and 85 borderline for shape. Medians (10th-90th percentile), fit /
  borderline: spread 0.64 (0.54-0.74) / 0.63 (0.56-0.74); trend 0.34 (-0.62
  to 1.55) / 0.47 (-0.63 to 1.32); H 0.45 (0.25-0.56) / 0.41 (0.22-0.62);
  ratio 1.016 (0.96-1.12) / 1.018 (0.97-1.11); quartz core share 0.01
  (0-0.18) / 0.03 (0-0.30). The two groups agree, so borderline photos add
  numbers without shifting the spread. The trend's median is positive, as in
  [@goldbaum2019], but at least a tenth of the photos read negative. The core
  share counts patches the map scores at 0.5 or more, and reads low.

## Amendment: step 3, simulations blurred like photos (2026-10-25)

- **How.** `agatesim volume shape` (`cut_shapes.py`) takes each 3D preset, draws
  12 settings from its Randomize ranges (`explore.vary_model`, full strength;
  the H2 nodule has none, so one draw), and cuts each draw at 2 random planes
  (`random_cuts`). Each cut is made to look like one fit or borderline library
  photo picked at random (143 photos; `library shape` now stores each photo's
  edge width, band spacing and noise):
  - it is sized so its bands are as many pixels apart as the photo's (a probe
    at 512 px, then 256-3072 px);
  - it is blurred until its edge width over band spacing is the photo's
    (photos: 0.23-0.49, median 0.38). Blur erases the finest bands and widens
    the spacing left, so the blur is found in up to four rounds;
  - grey noise of the photo's level is added.
  A cut whose edge per spacing ends more than 15% from its photo's isn't
  compared (cuts too coarse for a sharp photo). The face is the cavity; the
  quartz core share is the quartz phase's share of it.
- **Which settings move a statistic.** For each statistic, each setting's rank
  correlation with it is taken over draws (a draw's cuts count once, by their
  median). A setting is named only when its correlation beats the strongest
  that any setting reaches with the results shuffled, in 95% of 500 shuffles:
  models have 20-40 settings, and a fixed threshold named palette colours by
  chance.
- **Cost:** 4,832 s for all 23 presets (552 cuts) and 3.16 GB peak (the H2
  nodule's lattice); cached in `references/models/cut-shapes.json`, after which
  the report takes 2 s.

Results (photos, fit and borderline pooled, 10th / median / 90th percentile:
spread 0.54 / 0.63 / 0.74; trend -0.63 / 0.42 / 1.45; H 0.23 / 0.42 / 0.61;
ratio 0.96 / 1.02 / 1.12; core 0 / 0.02 / 0.23). Per model: the median of its
compared cuts and the share below / above the photos' 10-90% range.

| preset | spread | trend | H | ratio | core |
|---|---|---|---|---|---|
| botryoidal-3d | 0.56 (39/11) | 0.67 | 0.30 | 1.01 | 0 |
| botryoidal-mechanistic-3d | 0.65 | **3.38 (0/85)** | 0.52 | 1.11 (0/40) | 0 |
| eye-3d | 0.55 (48/5) | 0.02 | 0.35 | 1.00 | 0 |
| eye-mechanistic-3d | **0.54 (55/10)** | 0.31 | 0.34 | 1.01 | 0 |
| fortification-3d | **0.55 (50/0)** | 0.39 | 0.30 | 1.02 | 0 |
| fortification-mechanistic-3d | **0.45 (78/0)** | 0.55 | 0.34 | 1.02 | 0 |
| fortification-waterline-mechanistic-3d | **0.53 (52/4)** | 0.09 | 0.43 | 1.01 | 0 |
| liesegang-nodule-3d (2 cuts) | 0.50 | -0.79 | 0.33 | 0.94 | 0 |
| plume-3d | **0.53 (60/0)** | 0.16 | 0.33 | 1.01 | 0 |
| plume-mechanistic-3d | **0.54 (50/0)** | 0.22 | 0.36 | 1.02 | 0 |
| quartz-geode-3d | **0.51 (61/0)** | 0.07 | 0.29 | 1.02 | 0.15 |
| quartz-geode-mechanistic-3d | 0.63 | 0.03 (29/6) | 0.54 | **0.94 (59/0)** | 0.18 |
| seam-mechanistic-3d | **0.48 (64/7)** | -0.02 (16/26) | 0.37 (38/0) | 0.99 | 0 |
| stick-3d | **0.46 (86/0)** | 0.32 | 0.29 | 1.01 | 0.02 |
| stick-mechanistic-3d | 0.56 (42/0) | 0.16 | 0.34 | 1.04 (8/25) | 0.02 |
| tube-3d | **0.51 (67/0)** | 0.28 | 0.36 | 1.02 | 0 |
| tube-mechanistic-3d | **0.48 (67/17)** | 0.17 | 0.37 | 1.02 | 0 |
| waterline-3d | 0.60 (33/14) | 0.40 | 0.32 | 1.02 | 0 |
| waterline-mechanistic-3d | 0.62 | 0.04 (27/18) | 0.55 | **0.96 (57/24)** | 0 |

The four moss presets compare only 3-8 of 24 cuts each (few bands among the
dendrites) and are left out of the table; none sits outside the photos' range.

- **Bands are too even in most models.** In 11 of the 18 presets with more
  than two cuts, half or more of the cuts' thickness spreads are below the
  photos' 10th percentile (bold), and in three more 39-48% are. Photos and
  simulations share the spread's low reading (step 2), so this is a real
  difference. Only botryoidal-, quartz-geode- and waterline-mechanistic sit at
  the photos' median.
- **Botryoidal-mechanistic's bands thicken far too steeply inward** (trend 3.4
  against the photos' 90th percentile of 1.45, in 85% of cuts).
- **Quartz-geode- and waterline-mechanistic bands thin inward** (ratio 0.94-0.96,
  more than half the cuts below the photos' range).
- Roughness (H) and the quartz core share sit within the photos' range
  throughout; procedural models lean smooth (H 0.29-0.36 against 0.42).
- **Which settings:** only one setting beats chance: in stick-mechanistic, longer
  sticks lower the trend (rho -0.95). Twelve draws are too few to name the
  settings behind the rest; step 4 needs either a decision from these results
  directly (e.g. widen the thickness-variability ranges), or more draws of the
  models chosen (about 6 s per cut).

## Amendment: step 4, wider Randomize ranges (2026-10-25)

- **48 draws per model** (owner's choice; 96 cuts each, 5.5 h, about 3 GB).
  The step-3 findings hold. Fifteen settings now beat chance on some statistic
  (about 5 of 110 would by chance alone). Thickness spread is moved by almost
  none of them: eye's period variability (+0.52) and plume's dendrite density
  (+0.57). Band period (moss, quartz-geode, tube) and band thickness
  (fortification) raise H; that may be partly the blur, which smooths wider bands
  less. Longer or more elongated sticks set the stick models' quartz core share
  (+0.79, -0.69); in botryoidal-mechanistic, wider spherulite spacing lowers the
  trend (-0.45).
- **Every model already has a thickness-variability setting** (period or
  thickness variability, supply noise, dose variability), and the measured
  spread rises with it only slowly: at the top of the old ranges, procedural
  spreads reach about 0.59 against the photos' 0.63. Fitted lines put the photos'
  median at a log-normal sigma of about 1.0-1.2, and at supply noise 0.3-0.75
  where it helps at all.
- **Ranges changed** (Randomize only; presets and their verified results are
  untouched): period and thickness variability 0.1-0.8 to 0.1-1.2; supply noise
  0-0.3 to 0-0.6; spherulite spacing 6-14 mm to 13-24 mm; spherulite rate
  variability (front feedback) gains a range, 0-0.6. Botryoidal criteria still
  pass on all 20 random cuts at spacings of 10, 14, 18 and 22 mm. The seven
  botryoidal photos in the library have a trend of -0.07 (-0.60 to 0.91), flatter
  than the library as a whole. No source gives the spread of band thickness, so
  the library is the reference (as above), and these settings stay effective.
- The cut cache's key now includes the model's schema, so a changed range
  redoes that model's cuts.
- **Re-check** (12 draws per model, 80 min). The spread rose by 0.02-0.10 in
  most procedural models (cuts below the photos' range: fortification 58% to 41%,
  tube 71% to 52%, botryoidal 51% to 29%). Half or more of the cuts are still too
  even in 9 of the 22 models (stick, seam, tube, both fortification-mechanistic
  presets and several moss presets). Botryoidal-mechanistic's trend fell from 2.9
  to 2.0, but 62% of its cuts are still above the photos' range. Unchanged models
  shift by up to about 0.02 in median and 10 points in share between the 48- and
  12-draw runs, so smaller moves are noise.
- **What this means.** Wider ranges close only part of the gap: thicker and
  thinner bands in sequence are not enough. One untested explanation is that a
  photographed band's width varies along its own length (pinching and
  swelling), while a simulated band keeps one thickness all the way round.

## Amendment: step 5, band contrast (2026-10-25)

- **Pinch and swell is not testable by these statistics.** A profile crosses
  each band once, so a band that is thin where it is crossed reads the same
  whether it is thin everywhere or pinches there. On synthetic concentric bands
  degraded like 24 library photos, along-band width changes (log amplitude
  0.5) raised the measured spread exactly as more band-to-band variability
  does. The measured spread also levels off near 0.6: a log-normal sigma of
  1.2 (true CV about 1.8) reads 0.59, because blur and the turn threshold even
  out the widths. Varying band contrast (log-normal sigma 0.7) raised it
  separately, by 0.04-0.15: a band too faint to make a turn joins its
  neighbours into one wide band.
- **A sixth statistic, contrast spread** (`specimen.shape`): the coefficient of
  variation of each band's brightness swing between the turns that bound it,
  the median over profiles. On synthetic faces it reads 0.02 for even bands,
  0.06 for bands of uneven width only, and 0.20 for bands of uneven contrast
  only (true value about 0.2); the even face is its negative control.
- **Photos** (`agatesim library shape`, 5 min): 0.44 (10-90%: 0.36-0.54), alike
  for fit and borderline photos.
- **Cuts** (12 draws, 83 min): most models are below the photos. Medians 0.30-0.40 in
  most models (procedural ones included), lowest in fortification-mechanistic
  (0.17), moss-mechanistic (0.26), plume-mechanistic (0.31) and tube (0.33);
  only the two waterline models (0.43, 0.45) sit at the photos' median.
  Seam-mechanistic is the opposite case: contrast fine (0.42), widths far too
  even (spread 0.38, 91% of cuts below the photos). In fortification (procedural)
  lower alternation (more random milkiness) raises the spread (-0.89), as the
  contrast effect predicts.
- **Limits.** Photos' swings also carry lighting, colour and texture that a
  render lacks, so part of their contrast spread may not be banding at all.
  Twelve draws move a share by about 10 points, so the per-model figures are rough.

## Amendment: step 6, contrast variability (2026-10-25)

- **A procedural setting, `contrast_variability`** (imposed; procedural
  fortification and procedural growth, 2D and 3D): each band's milky/clear
  swing is scaled by a log-normal factor of mean 1 and this log spread, drawn
  from its own stream so band widths, iron and the sign of each swing are
  unchanged. Default 0, so presets and verified results are unchanged; the
  Randomize range is 0-0.6. The waterline models already match the photos and
  do not get it.
- **Not in the mechanistic models** (owner's choice): a knob with no mechanism
  behind it would hide what their low spread shows.
- **Why fortification-mechanistic reads 0.17.** Front feedback makes each band
  either milky or clear, two fixed values (ADR 0048's assumption), so every
  band swings by the same amount; only the iron stain varies. A low contrast
  spread is what that assumption predicts, not a fault in the statistic.
