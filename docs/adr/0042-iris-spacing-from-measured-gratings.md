# 42. The iris spacing test follows measured gratings

- Status: accepted (owner approved, 2026-10-17)
- Date: 2026-10-17
- Amends: `grating-spacing` (iris), set in [ADR 0010](0010-optical-renderer.md)
- Follows: [ADR 0041](0041-reading-for-shadow-iris-and-plume.md)

## Context

`grating-spacing` asked for a median visible micro-band spacing of 0.5–5 µm.
That range came from the review's figure for oscillatory zoning of defects
([@cartwright2026] §5.1.1), not from measured iris gratings. Jones measured
iris gratings from about 15,000 down to 400 lines per inch, about 1.7–64 µm,
and noted that coarser gratings still diffract, with colours close to the
beam ([@jones1952], read in ADR 0041). So the test would have rejected real
iris agates with coarse gratings.

## Decision

- **New range: 1–65 µm**, sourced to Jones's measurements, with a small margin
  below his finest grating. The metric's description says so.
- The procedural model's `micro_band_um` now accepts up to 100 µm (was 50), so
  spacings beyond the measured range can be set.
- **Negative controls** (`tests/test_criteria.py`): micro-banding at 0.5 µm and
  at 80 µm, outside the measured range, fails `grating-spacing`. The old
  control, which rejected 20 µm as "not the reported iris structure", is
  replaced by a check that a 20 µm grating now passes. `spectral-dispersion`
  is unchanged: it tests the renderer against the grating equation, so it can
  pass for any spacing whose first order reaches the visible range at some
  band orientation.

## Results

- The iris verification preset still passes (median spacing 2.16 µm).
- Without micro-banding, or with it hidden by pigment, iris still fails both
  tests, as before.

## Consequences

- A mechanistic iris (ADR 0041, §2) may produce micro-bands anywhere in
  1–65 µm, not just near 2 µm.
