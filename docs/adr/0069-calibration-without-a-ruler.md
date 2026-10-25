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
