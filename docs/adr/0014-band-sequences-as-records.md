# 14. Band sequences as records: forcing input and sequence statistics

- Status: accepted
- Date: 2026-10-15
- Builds on: [ADR 0013](0013-mechanistic-front-feedback.md)

## Context

The H1 model's bands are far more regular than natural ones (ADR 0013). The
owner asked whether the irregularity of natural banding is better treated as a
signal of the local environment than as noise. If so, how should the simulator
model it, so that such signals could be recovered?

The literature pass found:

- **Holten et al. [@holten1997] (read in full).** They analysed zoning profiles
  in three other minerals with the width method, w(l) ∝ l^H.
  - The profiles were scale-free, with H mostly 0.25–0.45 (anti-persistent),
    with no periodic component and no detectable chaos. They read this as
    environmental forcing passed through almost unfiltered.
  - A periodic, self-organised record looks different: w(l) has slope ≈ 1 below
    the period and ≈ 0 above it.
  - They expect closed systems such as agate to be internally driven.
- **Torii & Miura [@torii2024].** Impurity *inhibition* (step pinning plus
  bistability) is another internal oscillator. Its feedback has the opposite
  sign to our catalysis.

## Decision

1. **Forcing as an input, not jitter.** H1 gets an optional fluctuation of the
   bulk silica supply:
   - `supply_noise`: standard deviation;
   - `noise_time`: shortest time scale;
   - `noise_hurst`: Hurst exponent.

   The fluctuation is drawn by spectral synthesis on its own time axis, from
   the run's seed, so it doesn't depend on the grid. Its record is kept in the
   front history for experiments.
2. **Sequence statistics** (`agatesim.sequence`). They read Fields only, so
   they apply to simulations and photos alike:
   - the impurity profile against depth;
   - Holten's width scaling and Hurst exponents below and beyond the dominant
     wavelength;
   - a spectral-peak prominence;
   - cycle thicknesses, with their CV and lag-one autocorrelation.
3. **An identifiability experiment** (H1 fortification preset). Known forcings
   are imposed, then read back from the bands (results below).

## Results

**Sensitivity.** The default oscillator lies near its onset, so it amplifies
its environment:
- A 5% supply fluctuation raises the cycle-thickness CV from 0.09 to 0.12–0.9.
- The spectral peak's prominence falls from about 45,000 to 7–1,800, so a
  forced rhythm is easy to tell from a free one.

**What the bands record.** Cycle thickness follows the mean supply over the
cycle (more silica, thinner and shorter cycles):
- r = −0.4 to −0.8 for thickness;
- up to −0.98 for cycle duration;
- with 12–18 cycles, across forcing amplitudes of 5–30%, correlation times
  below and above the cycle, and Hurst exponents of 0.3 and 0.7.

The forcing's *level*, cycle by cycle, is therefore recoverable from the band
sequence, given the model.

**What the bands don't record.** With about 60 cycles, the cycle-thickness
sequence gave H ≈ 0.3–0.5 whatever the forcing's H (0.2–0.8). The forcing
itself, averaged per cycle, keeps H = 0.44–0.78. The oscillator's nonlinear
response rewrites the statistics.
- So generic scaling statistics of the bands don't reveal the forcing's
  character.
- An anti-persistent H in natural records need not come from anti-persistent
  forcing, as Holten et al. assumed for other minerals. In this model, an
  internal oscillator under forcing produces similar values.

**The owner's photos** were analysed privately; nothing was committed. They are
far more irregular than the model: cycle CV 1.4–4.2. Their H below the dominant
length was mostly 0.25–0.47. These are indicative only: photo colour is a poor
proxy for trace elements, and wall distance is only a stand-in for growth order.

## Consequences

- **Signals are best harvested by inversion through a mechanism model,** not
  by generic statistics. For each candidate mechanism, fit the forcing level
  cycle by cycle (or by simulation-based inference) and compare mechanisms by
  how well they explain the sequence. This becomes the core of M10's
  "conditions from photos".
- **Separating signal from intrinsic dynamics** needs more than one specimen.
  Nodules that grew in the same environment should share its slow component,
  while band-by-band detail differs [@cartwright2026]. Comparing neighbouring
  nodules is the natural test. The owner's six Hebei nodules may allow it if
  they come from one locality.
- **More than one observable per cycle** (thickness, impurity contrast,
  translucency, micro-band spacing) can separate forcing variables, such as
  silica supply against temperature.
- **The model's regularity is no longer a free knob.** Irregularity enters as an
  explicit, documented forcing whose record can be compared with what the
  bands show.
