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

## Consequences

- The owner's marks become the benchmark for tuning the tracing: thin bands,
  corners, and real-photo ring closure. Each change can then be judged by
  recall and precision on real specimens, not only on synthetic ones.
- Marks stay on the owner's machine like the photos, and are never committed.
