# 26. A corner benchmark from high-resolution photos

- Status: accepted (five photos; time-boxed)
- Date: 2026-10-16
- Builds on: [ADR 0015](0015-mechanistic-liesegang.md), [ADR 0022](0022-corners-at-the-bands-own-corner.md)

## Context

The mechanistic corner question is whether fortification's sharp corners come
from growth at the wall (H1 keeps them) or from precipitation controlled by
diffusion through the cavity (H2 rounds them; ADR 0015). Answering it from real
agates needs photos sharp enough to resolve a corner well below one band
spacing. The owner suggested looking for close-up, higher-resolution images.

## Decision

1. **Photos.** Five photos of polyhedral agates from Sítio Garguelo, Brazil,
   at 4,700–7,300 px. They are by Marie-Lan Taÿ Pamart, CC BY 4.0, from the
   MNHN Caillois donation on Wikimedia Commons. The owner approved the
   download. `scripts/fetch_reference_images.py` fetches them into
   `references/images/full/`, which is gitignored, and checks each file
   against its published size.
2. **Measures** (`agatesim.specimen.corner_fit`), tested on synthetic corners
   of known radius:
   - **Mitre turn width.** The mitre is the line where bands from two faces
     meet. At stations along a mitre marked by hand, the band-normal direction
     is sampled across it, from the colour structure tensor at 3 px. The turn
     width is the distance over which it covers the middle half of its swing,
     which is the criterion's definition. It is divided by the band spacing,
     taken from strong boundaries on the arms.
   - **Seam width.** In these agates the mitre is itself a visible seam,
     because the same band looks different on the two faces. Bands turn at the
     seam, so the seam's width (FWHM of the colour gradient) bounds the turn
     width from above.
   - A fully automatic corner finder (fitting arms and fillet to detected
     edges) works on synthetic corners but not on the photos. It fits quartz
     texture and botryoidal surfaces, so corners are marked by hand, as band
     boundaries were in ADR 0019.

## Results

Four mitres in `polyhedral-agate-caillois-donation-mnhn-n02` (a 5038 px photo),
marked on 800 px crops:

| Mitre | Band spacing | Seam width | Seam / spacing | Turn width / spacing |
|---|---|---|---|---|
| bottom-left corner | 189 px | 6 px | 0.03 | 0.11 |
| bottom-right corner | 122 px | 9 px | 0.07 | 0.31 |
| inner triangle, left | 121 px | 5 px | 0.04 | 0.23 |
| inner triangle, right | 64 px | 7 px | 0.11 | 1.10 |

- **The corners of these agates are sharp.** Bands from two faces meet at a
  seam 5–9 px wide, 0.03–0.11 of a band spacing. That is far below the
  criterion's threshold (0.7) and H2's rounding (1.6–2.4 band spacings,
  ADR 0015). It is consistent with sharp-cornered growth from the walls (H1,
  procedural fortification).
- **Turn widths from band direction read higher** (0.11–0.31, and 1.1 on the
  narrowest mitre). The seam itself and fine fibrous texture pull the
  direction field off. Seam width is the cleaner bound here.
- **Models measured the same way.** H1 and procedural slabs at 1536 px give
  turn widths of 4–5 px, the measure's own floor at its 3 px scale, so their
  corners are sharp as far as it can tell. That is 0.24–0.38 of their band
  spacing, only because the bands are 13–16 px apart at this resolution. The
  measure can't read H2's slabs: their dense rings defeat the spacing
  estimate. The criterion's own H2 values stand.

### All five photos

Corners were marked on gridded 800 px crops at full resolution. Where nested
bands meet at a mitre, the mitre measures apply. Where only one boundary turns,
`measure_marked_boundary` fits arms and a fillet to the long boundary nearest
the mark (texture edges excluded). It takes the band spacing from the nearest
neighbouring boundary.

| Photo | Corner | Measure | Turn width / band spacing |
|---|---|---|---|
| n02 | four mitres | seam width | 0.03, 0.07, 0.04, 0.11 |
| n04 | top corner | mitre: seam width / band direction | 0.40 / 0.37 (thin bands, 35 px apart) |
| n03 | top-left, inner edge of the pale layer | fillet fit | 0 (radius under the 3 px floor; turn 108°) |
| n01 | right corner, white band | fillet fit | 0.63 (radius 223 px, turn 73°) |
| polygonal | top corner, inner bands | by eye | visibly rounded arcs; the turn (about 25°) is too gentle to fit |

- A further four corners could not be measured. Two on n04 show no corner at
  full resolution. n01's top and bottom-left are wavy or confused, and its
  marked boundaries didn't fit.
- **H1 and procedural slabs at 4096 px** have bands 36–43 px apart. They read
  0.09–0.17 band spacings, turn widths of 4–6 px, which is the measure's floor
  at 3 px.

**So real fortification corners differ between specimens:**

- **Sharp (three of five photos).** In n02, n03 and n04 the corners are as
  sharp as these photos resolve, within 0.03–0.4 band spacings. That matches
  H1 or procedural lining at the same relative resolution.
- **Rounded (two of five).** n01's right corner rounds over 0.63 spacings,
  just inside the criterion's threshold (0.7). The polygonal agate's inner
  bands round at a very obtuse corner. Neither approaches H2's 1.6–2.4.

No photo shows the strong rounding H2 produces. Moderate rounding does occur in
real agates, so a mechanism that never rounds is also not the whole story.

## Consequences

- Across five specimens, corners range from as sharp as the photos resolve
  to moderately rounded, but never as rounded as H2's. That strengthens the
  case of ADR 0015 with real data, and leaves room for a mechanism with some
  rounding, such as a regularised H1 (ADR 0017 backlog).
- Backlog:
  - more specimens, ideally with a scale;
  - teach the direction measure to step over a seam;
  - H2 and a regularised H1 measured at the photos' relative resolution.
