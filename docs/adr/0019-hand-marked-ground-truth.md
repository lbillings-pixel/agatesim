# 19. Hand-marked band boundaries as ground truth for photos

- Status: accepted
- Date: 2026-10-15
- Builds on: [ADR 0012](0012-band-tracing-along-the-band-direction.md), [ADR 0018](0018-mechanism-discriminants.md)

## Context

Synthetic photos can't tell how well band tracing works on real specimens.
ADR 0018 found that ring closure separates the mechanisms on synthetic photos
but reads 0.00–0.16 on all eight of the owner's photos, which looks like a
tracing failure on real bands. To measure that, the analysis needs ground truth
from real photos. The owner offered to provide it by hand.

## Decision

1. **Marking in the Specimens screen.** The owner:
   - draws a line across the face (two clicks, from the outer wall inward);
   - clicks each band boundary along it. Clicks snap to the line, and clicking a
     mark again removes it;
   - zooms (1×, 2× or 4×) to see fine bands.

   Several lines can be marked per photo.
2. **Storage.** The lines are stored with the photo's other settings in
   `specimens/.agatesim/<photo>.json`, which is local and gitignored. Positions
   are fractions along the line in working-photo pixels, independent of the
   analysis grid and the scale.
3. **Scoring** (`agatesim.specimen.benchmark`):
   - The traced band boundaries along the same line are found, with slivers
     under 2 analysis pixels ignored.
   - They are matched one-to-one to the marks, closest pairs first, within a
     quarter of the median marked spacing (at least 0.2 mm).
   - Reported per line: marked, traced, matched, recall (marks found), precision
     (traced boundaries that are real) and mean offset.

   The analysis shows this as a table, with marks (yellow) and traced
   boundaries (cyan) drawn on the photo.
4. **Tests.**
   - The scoring has a unit test.
   - On a synthetic photo, marks placed where the simulated bands truly change
     must be found (recall and precision over 0.6).
   - The server round-trips the lines and returns their scores.
   - The marking geometry has web unit tests.

## Amendment (2026-10-15): first results, chance level, full-resolution edges

The owner marked 164 boundaries along four lines on three photos. The marks
are about 0.35 mm apart (median), finer than the 768-px analysis grid
resolves. Results (summary numbers only, as the photos are private):

- **Chance level.** With marks this close, randomly placed boundaries match many
  of them. Each score now reports `chance_recall`, the mean recall of as many
  boundaries placed uniformly between the first and last mark (200 seeded
  draws). The minimum tolerance drops from 0.2 to 0.1 mm, which is about how
  precisely a boundary can be clicked at full resolution.
- **The band tracing** found 7–24% of the marks, close to chance. On finer
  grids its recall rose, but its precision fell to 0.33–0.47.
- **A full-resolution boundary detector** (`agatesim.specimen.edges`) works in the
  photo's own pixels, about 0.07 mm each. It averages along the band direction,
  and keeps colour changes across the bands that peak and reach half the
  median peak strength.
  - On the owner's lines it found 61–73% of the marks, against a chance level
    of 24–35%, with a precision of 0.38–0.76.
  - On a synthetic photo it found 0.83 of the marks, with a precision of 0.85.
  - Its settings were chosen from about 20 tried on the same lines, so these
    real-photo figures are somewhat optimistic.

  The analysis now reports the detector's score next to the tracing's, and draws
  its boundaries in orange. It finds boundary positions, not band regions, so it
  doesn't replace the tracing behind the observed fields.

**What the photos can give.** These photos have uneven lighting, wet surfaces
and about 0.07 mm per pixel. Band positions can be measured from them to
within this accuracy. Finer band statistics (thin-band spacing, ring closure)
need better photos: higher magnification, even diffuse light and a polished
dry face. The owner and Claude agreed to stop tuning photo band detection here
and move to the other milestones.

## Consequences

- The owner's marks become the benchmark for tuning the tracing: thin bands,
  corners, and real-photo ring closure. Each change can then be judged by
  recall and precision on real specimens, not only on synthetic ones.
- Marks stay on the owner's machine like the photos, and are never committed.
