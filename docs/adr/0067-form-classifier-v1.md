# 67. A learned form classifier, v1: DINOv2-small through ONNX Runtime

- Status: accepted (M32 part 1, stage 3 of [ADR 0063](0063-specimen-work-restarted-in-stages.md))
- Date: 2026-10-24

## Context

ADR 0063 section 3 joins the criteria with a learned classifier: a pretrained
image model run locally, a small classifier on top, trained on labelled
reference photos and rendered simulations, answering several forms with a
confidence or "undetermined". It asks this ADR to record the model, its one-off
download and its measured time and memory. The project had no machine-learning
software. The owner chose, of three offered (DINOv2 through ONNX Runtime;
PyTorch on the GPU, about 2.5–3 GB; CLIP through ONNX Runtime), the smallest:
DINOv2-small [@oquab2023] through ONNX Runtime, on the processor.

When this was decided the owner had labelled about half of the 300 library
photos ([ADR 0066](0066-reference-library-and-labelling.md)): 127 show forms.

## Decision

### 1. The model

- **DINOv2-small** (ViT-S/14, Apache-2.0), the ONNX export at
  `onnx-community/dinov2-small`, pinned to revision `8b1f705a` and checked by
  SHA-256 on arrival. `agatesim classify fetch` downloads it once (84 MB, 50 s
  here) into `references/models/` (gitignored), with the embeddings cache and
  the trained classifier.
- **ONNX Runtime** (CPU build, 14 MB) is the only new dependency. It runs on the
  processor: at 95 ms per photo the GPU is not needed at this scale, and the GPU
  build would bring CUDA libraries beside CuPy's. This departs from "on the GPU
  when there is one" in ADR 0063; a GPU build can be added if the library grows
  by orders of magnitude.
- A photo is prepared as the model expects (shortest side 256 px, bicubic,
  centre crop 224 px, ImageNet mean and spread). Its embedding is the class
  token beside the mean of the patch tokens (768 numbers), scaled to unit length.

Measured on this PC (16 logical processors): model load 0.2 s and about 100 MB;
22 ms to prepare and 73 ms to run per photo; the 300 library photos in 28 s,
peak 181 MB. The first training run embeds the labelled photos (17 s) and
renders and embeds 390 simulated slabs (173 s), peak about 230 MB; later runs
read the cache and take about 2 s.

### 2. The classifier

One logistic regression per form on the embeddings (L2 penalty, L-BFGS through
SciPy). Rare forms are weighted up by the square root of their rarity
(`BALANCE = 0.5`). A form is reported when its probability reaches 0.5; when
none does, the answer is "undetermined", with every form's probability kept for
display.

### 3. Training data

- **Labelled library photos** whose verdict is "forms", one count each.
- **Simulated slabs:** 30 seeds of each form's procedural preset at 320 px,
  turned, flipped and recoloured (real agates come in every orientation and
  many colours), each counting 0.1 of a real photo. Shadow and iris are shown
  as they are seen, as in the gallery.

### 4. Evaluation: specimens held out, not photos

Five-fold cross-validation on the labelled photos. Photos that probably show one
specimen (crops, details, numbered copies, judged from their ids) share a fold,
so no test photo has a near-copy in its training set. `agatesim classify
evaluate` prints the results.

The settings were chosen on these same folds from a small grid (rare-form
weighting 0, 0.5 or 1; penalty 0.1, 1 or 10; simulations 0 or 0.1), so the
figures below are somewhat optimistic:

| | |
|---|---|
| most likely form is among the labels | 87% (always "fortification": 70%) |
| every reported form right, at least one reported | 69% |
| reported forms that are right, pooled | about 80% |
| labelled forms found, pooled | about 60% |
| undetermined | 1% |

Per form: fortification, moss, botryoidal and iris are reported reliably (right
85–100% of the time when reported); quartz-geode and eye are middling; waterline,
fortification-waterline and tube are rarely found; seam, plume, shadow and stick
(3–5 labelled photos each) are never found yet.

Rendered slabs barely change the held-out results at weight 0.1, and at higher
weights they find more forms but raise more false alarms. Our renders still
look unlike photos (no host rock, no photographic light); making them look more
like photos is a later lever, not part of v1.

On the committed reference photos (`references/images/`), six are not in the
library, so the classifier never saw them. It found 6 of their 13 catalogued forms;
the criteria-based identification recorded in the snapshot finds none of the 24.
The snapshot test stays criteria-only, since CI has no model file.

### 5. What it is not

A form classifier recognises appearance. Trained on simulations or not, its
answers are never evidence for a formation mechanism, and a criteria pass stays
the stronger evidence (ADR 0063).

## Consequences

- `agatesim classify fetch|train|evaluate|photo <path>`. CI tests use a stand-in
  embedder; a test of the real model runs only where the model file exists.
- Typed wrappers `_onnx.py` and `_scipy.minimize_lbfgs` keep strict type
  checking elsewhere.
- More labels should help the rare forms most: the owner's next batches are the
  main lever, then photo-like renders.
- M32 part 2: answers on the Classify screen, with progress and an estimate, and
  the owner's corrections as labels.
