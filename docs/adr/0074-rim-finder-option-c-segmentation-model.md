# 74. The rim-finder, option C: a promptable segmentation model

- Status: accepted (2026-10-29; owner chose to pursue C, keeping ADR 0073's
  held-out run and a review of the bar in reserve, and approved the download)
- Date: 2026-10-29
- Builds on: [ADR 0073](0073-rim-finder-for-library-photos.md), [ADR 0067](0067-form-classifier-v1.md)

## Context

ADR 0073's method B (DINOv2 patch graph, then the colour-gradient watershed)
passes two of its three bars on the 80 tuning photos but not the one that
matters most: of the outlines it returns, 28 of 36 judged follow the rim
(78%; bar 90%). Its misses are things colour and patch features cannot
settle: two halves side by side read as one object, loops into the
backdrop next to stand clips, a geode's inner cavity taken for its rim, and
no score that tells good outlines from bad (ADR 0073 section 5). ADR 0073
named the next step: a dedicated segmentation model, prompted by B's mask.

## Decision

### 1. Model

**SAM 2.1 Hiera-Tiny** [@ravi2025], run through ONNX Runtime on the
processor, like the classifier's model.

- Peer-reviewed (ICLR 2025); on single images it matches or beats the
  original Segment Anything [@kirillov2023] (SA-23 one-click mIoU 61.9
  against 58.1) and runs about six times faster. Tiny has 38.9 M parameters;
  no separate image-task scores are published for it.
- Licence: Apache-2.0 for code and weights.
- File: the `onnx-community/sam2.1-hiera-tiny-ONNX` export, pinned at
  commit `814a066640debee5a91e70aa401fb8e17e030503`, full precision:
  image encoder about 134 MB and prompt decoder about 21 MB, **about 155 MB
  in all**, saved to `references/models/` (gitignored) with SHA-256 hashes,
  fetched by the existing pinned-download code. The export has no model
  card of its own; its licence is the original's. Inputs: points and boxes.
  Outputs: three masks per prompt, a predicted IoU for each, and an
  object-presence score.
- Time: the image encoder dominates. The only processor timing found is for
  the larger B+ model, 1.2 s per photo on a 14-core server [@sun2024];
  Tiny is expected below that. Measured on 10 photos first (time and
  memory), and `agatesim.estimate` updated.

Held in reserve, each a separate download needing approval:
EfficientViT-SAM-L0 (Apache-2.0, the authors' own ONNX export, about
140 MB, fastest in [@sun2024]; a workshop paper, 512 px input) and SAM
ViT-B (about 375 MB, about 3 s per photo) as a reference.

### 2. Method

1. B's first stages are kept: the patch graph, the background side, the
   stone's patch component and its declines (no single object, implausible).
2. SAM 2.1 is prompted with the box around B's patch mask (widened by half
   a patch), positive points at the mask's deepest interior points, and
   negative points on large non-stone areas inside the box (stand clips,
   the gap between two halves). The patch mask itself is not given as a
   prompt: SAM expects its own low-resolution logits there [@kirillov2023].
3. Of the three masks returned, the one chosen is the one with the highest
   predicted IoU among those that agree with B's patch mask (IoU at least
   0.7). A geode's cavity, much smaller than the patch mask, is ruled out
   that way.
4. **Declines**, all on the 80 only: predicted IoU below a threshold
   (starting at SAM's own 0.88); stability below 0.95 (the masks at logits
   −1 and +1 differ); object score below zero; no mask agreeing with B;
   frame contact; two pieces of like size (as in B). SAM's predicted IoU
   alone tracks the true IoU only loosely (r = 0.49 on COCO for SAM 2
   [@kaiser2025]), hence several signals rather than one.
5. SAM's masks come at 256 × 256 and are scaled up. If the boundary is
   judged too coarse on the 80, a narrow-band watershed on the colour
   gradient refines it, as in B.

Known risks from the literature: nearby objects of like appearance (two
halves) [@ravi2025, App. C]; fine structures and crisp boundaries
[@kirillov2023, Sec. 8]. Label cards
and frames may still be taken as the object.

### 3. How it is judged

Unchanged from ADR 0073 section 3: the same split
(`references/rim-split.toml`), the same synthetic tests and controls, the
same bar (of outlines returned at least 90% follow the rim; an outline on at
least 60% of photos with the rim in frame; at least 90% of cut-off photos
declined), helper-agent yes/no on the 150 held out, and the owner's check of
20 "yes" and 10 "no" on nodule's check page. The friend's photos are
reported separately. Tests needing the model are skipped where it is not
fetched (CI).

### 4. If C misses the bar

Back to the owner, with the options kept in reserve: ADR 0073's held-out
run for the better of B and C, or a review of the bar (for instance
reporting the error rate alongside nodule's measures).

### 5. Tuning record (2026-10-29)

Built as `agatesim.specimen.sam` (fetch: `agatesim classify fetch
--segmenter`) and used by `find_rim` where the model is fetched. The export
takes points and boxes but no mask, as expected. Measured on 10 library
photos: about 2.1 s per photo where the model runs (0.6 s where the patch
stage declines first), 1.2 GB peak; without ONNX Runtime's memory arena the
encoder peaks at 0.9 GB instead of 1.7 GB, for about 0.1 s more.
`agatesim.estimate.find_rims` carries these figures. Synthetic stones pass
(SAM's chosen mask overlaps the true outline at 0.97-0.99; the controls give
no outline).

On the 80, with the confidence declines first switched off so that every
outline could be judged (by Claude and one helper agent, on SAM's own
outlines: judgments inherited from B's outlines by overlap proved unreliable,
since a loop into the backdrop moves the overlap by under 5%):

- SAM's outlines followed the rim on 33 of 38 photos (87%; B 78%). A small
  opening of its mask removes thin spurs along stands.
- Neither SAM's scores nor agreement across prompt variants (box only,
  grown or shrunk box, no negative points) separate the remaining misses:
  they are confident and stable (a geode's inner cavity, two halves in one
  outline, a loop into a label card). Stability below 0.89 marked all five
  misses but also 13 of the 33 good outlines.
- Coverage was the binding limit: 16 photos with the rim in frame were
  declined at the patch stage because under 0.8 of the border fell on the
  backdrop's side (shadows, graded backdrops). With the model the patch mask
  only prompts it, and its mask still meets the frame test, so 0.6 is used
  with the model (B keeps 0.8).
- Settings: border majority 0.6, predicted IoU at least 0.88 (SAM's own
  default, untuned), stability at least 0.5 (a loose guard: no setting up to
  0.62 changed an outcome), object score at least 0 (every photo scored above
  17, so it never decides), negative points as in section 2.

Result on the 80: outlines on 39 of 59 photos with the rim in frame (66%;
bar 60%), 20 of 21 cut-off photos declined (95%; bar 90%), and 36 of 40
outlines follow the rim (**90%; bar 90%**, no margin). The four misses: a
close crop whose rim is cut off, a loop into a label card, a geode's inner
cavity, a ragged loop into a dark backdrop. The held-out set is untouched.

`find_rim(sam="auto")` uses the model wherever it is fetched and B
otherwise, so results depend on what is fetched; callers measuring the
library (nodule) should check `sam.fetched()` or pass the model explicitly.

## Consequences

- One download of about 155 MB, from Hugging Face, after the owner's
  approval; nothing leaves the PC. No new Python package (ONNX Runtime is
  installed).
- `find_rim` keeps its signature and reasons; B stays available as the
  first stage and as a fallback where the model is not fetched.
- The owner's time: approve the download; later, one check of about 30
  outlines.
