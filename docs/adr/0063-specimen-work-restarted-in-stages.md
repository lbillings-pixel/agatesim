# 63. Specimen work restarted in stages: classify first, calibrate second, replicate last

- Status: accepted (owner choices, 2026-10-24)
- Date: 2026-10-24
- Amends: [ADR 0006](0006-specimen-photo-analysis.md) (a learned classifier
  joins the criteria). Resumes the work paused in M10
  ([ADR 0018](0018-mechanism-discriminants.md), [ADR 0019](0019-hand-marked-ground-truth.md))

## Context

The Specimens screen was built for three purposes at once:

1. **Calibration**: the owner's photos as a reference that the models are
   tuned against.
2. **Classification**: photos inspected by the app, with or without help,
   and sorted into the archetype registry's forms.
3. **Replication**: the app's models reproducing a given specimen, as a test
   of how faithful the models are.

Doing all three together proved hard, and the work was paused (M10). An audit of
the code (2026-10-24) found the following:

- **Identification uses the archetype criteria only.**
  - On synthetic photos, a pass is reliable, but a fail says little.
  - Only botryoidal is detected well. Eye passes are not reliable.
  - Quartz, inclusions (tube, moss, plume) and optics (shadow, iris) are not
    detected at all.
- **Band tracing on the owner's photos finds boundaries at about chance level.**
  A full-resolution edge detector finds about twice as many (ADR 0019). Photo
  tuning was paused because the photos are near their limit.
- **No mechanism verdict is given for photos** (ADR 0018).
- **Parts of the code are unused.** Most of `corner_fit.py` is reached only from
  tests and scripts. The edge detector does not feed the observed fields.
  `analysis_ready` in the image catalogue is read by nothing.
- **ADR 0006's promise of regression tests on the reference images was not
  kept.** The tests check only the image catalogue.
- **ADR 0026's hand-marked mitre stations were never committed.** Those results
  can't be reproduced from the repository.
- **The screen has gaps.** Photos can't be deleted or renamed. Uploaded
  originals are stored as received, GPS included. They never leave the PC, but
  derived files are already metadata-free.

## Decision

### 1. Order and staging

Classification comes first, calibration second and replication last. The work is
done in milestones, each ending with a check-in. The owner may stop or reorder
the work after any of them.

| Stage | Milestone | Scope |
|---|---|---|
| 0 | this ADR | Audit and plan |
| 1 | M30 | Photo library with quality scores and "fit for" badges; Specimens screen split into Library and Classify; delete and rename; GPS stripped on upload |
| 2 | M31 | Reference library: a sources list, open-licence images first, a quick labelling screen |
| 3 | M32 | Classification v1: a local pretrained image model plus a small classifier; criteria kept as explanations; a confirm-or-correct loop |
| 4 | M33 | Feature detection: quartz core, inclusions, band boundaries |
| 5 | M34 | Calibration from photos that pass the quality gate |
| 6 | M35 | Replication and fidelity tests |

### 2. A quality gate for every photo

Each photo gets measured scores, each validated on synthetic photos that are
degraded on purpose:

- pixels per band spacing;
- sharpness;
- noise and JPEG artefacts;
- glare (clipped highlights);
- colour cast;
- whether a scale is present;
- above all, band contrast against noise.

The scores decide which uses a photo is fit for (classification, calibration).
Each badge says *why* a photo falls short, so that it doubles as photography
advice. Calibration (stage 5) uses only photos that pass.

### 3. A learned classifier alongside the criteria (amends ADR 0006)

ADR 0006 chose criteria alone, because a classifier needs many labelled
specimens and can't explain its answer. Criteria alone mostly answer "can't
tell" on real photos, so they are now joined by a learned classifier:

- **The model.** A pretrained image model runs locally (on the GPU when there
  is one). A small classifier sits on top of it. It is trained on labelled
  reference images and on rendered simulations: simulated slabs are free,
  labelled examples of each form's appearance.
- **Labels.** Each photo can carry several labels (forms, plus features such as
  a quartz core or inclusions). Each label has a confidence, and
  "undetermined" is an allowed answer.
- **The criteria stay.** They explain or back up an answer where they can read
  the photo, and a criteria pass stays the stronger evidence.
- **The owner's corrections become labels**, so the classifier improves with use.

The choice of model, its one-off download and the measured time and memory are
recorded in M32's ADR. A form classifier recognises appearance. It is never
evidence for a formation mechanism, whatever it was trained on.

### 4. External images in three tiers

Each image is recorded in a committed sources list (URL, licence, author, date
retrieved, tier). Images are fetched on demand into a gitignored folder, as the
corner-benchmark photos already are (ADR 0026). No external image enters the
repository unless its licence allows it (`references/images/` as now).

| Tier | Source | May be used for |
|---|---|---|
| 1 | Openly licensed or public domain (e.g. Wikimedia Commons, museum open-access collections) | Everything, including published classifier weights |
| 2 | Used by permission of the photographer or owner | What the permission covers, recorded in the sources list |
| 3 | All rights reserved, from sites whose terms allow it | Local evaluation and calibration only; never in published weights or committed images |

Tier 1 comes first. Tiers 2 and 3 need the owner's approval per source. This is
a risk judgement, not legal advice. Keeping images out of releases lowers the
risk but doesn't remove it. Copying is still copying, and site terms apply
whatever the copyright.

### 5. Privacy is unchanged

The owner's photos stay on the PC. No cloud vision service and no assistant
reads them. Everything derived from them is metadata-free, and they never train
weights that are published.

## Consequences

- M30 needs no downloads and no new dependencies. It can start at once.
- M31's main cost is labelling, done by the owner with the tool's guesses
  filled in beforehand. A few hundred tier-1 images is a realistic first
  library.
- M32 adds a dependency and a model download. Both are measured and approved
  before they are added.
- Replication (M35) separates two kinds of fit:
  - a **procedural** fit matches the look and tests nothing about mechanism;
  - a **mechanistic** fit is the fidelity test, and it waits for the calibrated
    measurements from M34.
- Loose ends from the audit are picked up where they fit:
  - **M30:** GPS stripped on upload; delete and rename.
  - **M31:** reference-image regression tests (ADR 0006 point 5); `analysis_ready`
    replaced by the quality gate.
  - **When corners are next needed:** ADR 0026's mitre marks committed.
