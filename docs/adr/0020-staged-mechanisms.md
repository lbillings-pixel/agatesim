# 20. Chained mechanistic stages for the combined form

- Status: accepted
- Date: 2026-10-15
- Builds on: [ADR 0007](0007-formation-history-and-growth-model.md), [ADR 0013](0013-mechanistic-front-feedback.md), [ADR 0016](0016-mechanistic-settling.md)

## Context

The combined fortification and waterline form was verified only at the
procedural tier. Its two parts are each verified mechanistically: wall-lining
bands by front feedback (H1), and horizontal layers by hindered settling (H4).
Real nodules record both orders. One example is a wall rim, then floor layers,
then bands draping over the floor. Another is floor layers first, then wall bands
above them.

The literature points to a change of conditions between the stages, not one
process that switches by itself. Lu and Sunagawa [@lu1994] (abstract) propose
that one silica solution does both. Small particles join the fibrous wall bands,
while particles grown past a critical size stay in suspension and settle out
later as Uruguay layers. Götze et al. [@goetze2020] §4.1.2 attribute Uruguay
bands to gravitational settling of flocculated silica. No source read so far
says what sets the moment of the switch.

## Decision

1. **A new model, `mechanistic-staged`** (`agatesim.models.staged`), runs the two
   verified mechanisms in turn. Each stage works only in the open space the
   earlier stages left:
   - **wall:** H1 grows inward from every solid surface, meaning the cavity wall
     and any earlier deposit. Distances are to the nearest solid, so later wall
     bands drape over a flat floor. The first wall stage stops once it has
     filled `rim_share` of the cavity. The last wall stage runs until the space
     is full or its silica runs out.
   - **floor:** H4 settles particle pulses in the open space left so far, using
     widths counted from that region's pixels. Layers pack up from its lowest
     point.
2. **What is imposed.** The stage order (`wall-floor-wall`, `wall-floor` or
   `floor-wall`) and `rim_share` stand for the timing of an environmental
   change. They are not properties of any band. `rim_share` is labelled
   `effective`. The bands and layers inside each stage, including their
   thicknesses and number, come from the mechanisms alone.
3. **Deposition time.** Stage *i* of *S* takes the times [*i*, *i* + 1)/*S*,
   so the archetype's `staged` criterion can read the sequence.
4. **Verification.** The preset `fortification-waterline-mechanistic` passes
   the unchanged combined criteria (two-domains, staged) at full resolution. Its
   result is 12 horizontal and 12 wall-parallel bands, in the sequence wall →
   horizontal → wall. The mechanistic status of the combined form is now
   `verified`. Tests cover:
   - each stage order gives its sequence;
   - the rim fills its share;
   - stages never overlap;
   - floor layers are horizontal and wall bands are wall-parallel;
   - previews match full runs.

## Consequences

- This verifies that the two mechanisms are *compatible* with the combined form
  when conditions change between them. It is not evidence for what causes the
  change.
- The particle-size switch proposed by Lu and Sunagawa could replace the
  imposed timing later, if a model of particle growth in the solution is added.
- Any other pairing can be chained the same way, for example H2 followed by H4.
