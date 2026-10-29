# 73. A rim-finder for library photos, and the friend's photos as tier 2

- Status: accepted (2026-10-29; owner chose B, the proposed bar, and both batches)
- Date: 2026-10-29
- Builds on: [ADR 0063](0063-specimen-work-restarted-in-stages.md), [ADR 0066](0066-reference-library-and-labelling.md), [ADR 0067](0067-form-classifier-v1.md), [ADR 0072](0072-reframing-a-coupled-follow-on-project.md)

## Context

Nodule (ADR 0072) measures outline shape (its C1–C3) and band count (C6) on
the library's 230 usable photos. It takes the outline from agatesim's
`segment()`, and in nodule's labelling the outline followed the stone's rim
on only 11 of 230 photos (nodule ADR 0004, section 8). The rest cut inside
the face, took in stand clips, or picked a small patch of a close-up whose
rim is not in the frame. The owner decided (2026-10-28) to improve the
outline-finding here, with its own tests and ADR, then move nodule's pin.

`segment()` was built for the owner's specimen photos: a blue cloth, a
ruler, an optional click. It feeds the specimen server, shape statistics and
the reference regression, so it stays as it is. Commons photos differ: white,
black or patterned backdrops, hands, stands and labels, and many close crops.

The owner checked 30 of Claude's yes/no outline judgments and agreed with all
30 (28 no, 2 yes; nodule fd66ebf). Claude's yes/no may therefore stand in on
held-out photos, but the "yes" side rests on two cases.

The owner's friend gave permission (2026-10-27) for local use and AI viewing
of photos he posts online (tier 2, ADR 0063), credited by a private alias.
Batch 2 (26 photos, 9 stones from Hebei, each cut once, wet and unpolished)
was saved by hand to the owner's Downloads folder on 2026-10-28.

## Decision

### 1. What a right answer is

The rim-finder returns either one outline that follows the rim of the whole
view (stone, slab or cut face, holes filled), or **no outline**, with a
reason: rim cut off by the frame, no single object found, or region
implausible. A wrong outline is worse than none, since C1–C3 measure
whatever outline they are given; so the finder declines when unsure.

A new module `agatesim.specimen.rim` (`find_rim(rgb) -> Rim`). `segment()`
is untouched.

### 2. Method (owner chose B, 2026-10-29)

- **A. Colour and edges only.** Learn the backdrop's colours from the frame
  border, grow the stone from the centre, refine the boundary with the
  existing colour-gradient watershed, then decline on frame contact. No new
  software or download; fast. Weak where the stone's colour matches the
  backdrop, on hands and on busy backgrounds.
- **B. DINOv2 patch features, then edges** *(recommended)*. The classifier's
  DINOv2-small model (ADR 0067) is already installed. Its patch features
  separate "stone" from "background" by what things look like, not just
  colour; the border patches seed the background. The coarse patch mask
  (14-pixel patches) is then refined to the pixel with A's watershed. No new
  software or download.
- **C. A dedicated segmentation model** (a "segment anything"-type model
  through ONNX Runtime, prompted by the image centre or by B's coarse mask).
  Likely best on clutter, but a new model download (tens to hundreds of MB)
  to vet, pin and measure, and slower on the processor.

Recommended: B, with C held in reserve if B misses the bar in section 3.

**Literature (2026-10-29).** B follows TokenCut [@wang2022]: a graph over the
patches, edges 1 where cosine similarity is at least τ and ε otherwise (τ =
0.2, ε = 1e-5, results nearly flat over τ 0–0.3), the second eigenvector
split at its mean, then the connected component holding the strongest
patch. LOST [@simeoni2021] and Deep Spectral Methods [@melaskyriazi2022] are
close relatives. What they don't support, so it is tested here, not assumed:

- They use the last layer's attention *keys*; the installed ONNX model gives
  only its final tokens. For DINO ViT-S, keys beat the other features by about 12
  to 28 CorLoc points [@melaskyriazi2022, Supp. Table 6]; DINOv2's final
  tokens are untested, so τ is tuned on the 80 tuning photos.
- Which side is the object: the papers take the side with the strongest
  patch or the smaller side, and both fail when the object fills most of
  the frame [@simeoni2021, Sec. 4.4], as close crops do. Here the side that
  holds most of the frame's border patches is the background, a rule of our
  own; with no clear majority, no outline.
- Frames and borders in a photo tend to be taken as the object
  [@melaskyriazi2022, Supp. Sec. 4]; label cards are expected to be a
  failure case.
- High-norm artifact tokens appear in DINOv2 ViT-L and larger
  [@darcet2023, Sec. 2.1]; ViT-S is likely, not certainly, free of them.

### 3. How it is judged

- **Split, fixed before tuning.** The 230 usable photos are split by a seeded
  draw into 80 for tuning and 150 held out. Nodule's 30 owner-checked photos
  go in the held-out set. Settings are chosen on the 80 only.
- **Held-out check.** Helper agents view each held-out photo with its new
  outline drawn on, and record two yes/no answers: is the whole rim in the
  frame, and does the outline follow it. Because the "yes" side is thinly
  tested, the owner checks a random 20 of the outlines judged "yes" (plus 10
  "no"), on nodule's check page. The owner's answer overrides Claude's.
- **Bar (owner accepted, 2026-10-29).** On the held-out set:
  - of the outlines returned, at least 90% follow the rim;
  - an outline on at least 60% of photos whose rim is in the frame;
  - at least 90% of photos whose rim is cut off get no outline.
- **Synthetic stones of known outline** (`agatesim.specimen.synthetic`): on
  plain, graded, textured and shadowed backdrops, one close in colour to the
  stone, and with a finger- or clip-like object touching it. Overlap (IoU)
  with the true outline at least 0.95 on plain backdrops and 0.90 on the
  others. Negative controls: a background-only image and a stone crossing
  the frame both give no outline.
- **The friend's photos are a hard test set** (section 4), never used for
  tuning, reported separately. In batch 2 fingers cover rims, three photos
  have text in the background and one an overlay, and the x1 photos show both halves of a stone; the right answer
  there is one half's outline or none.
- Time and memory are measured on 10 photos first. The estimate is a few
  seconds per photo on the processor, minutes for the library.

### 4. The friend's photos in the library (tier 2)

- Both batches are added: batch 2, and batch 1 (5 copies of one Hebei
  nodule sawn into a slab series, no scale; repeat shots of two faces give a
  small repeatability check). Batch 1's video stays out. Both are held out
  of tuning.
- Enforced in code (2026-10-29, before labelling them for Nodule's tags):
  `library.never_tuned_ids` (every tier-2 photo) is left out of classifier
  training, map training, tap-set choice and the band-shape calibration
  (`shapes.calibration_entries`); labels and `shapes.json` still cover them.
- Entries go into `references/library.toml` with `tier = 2`, the author
  as a private alias (`collector-1`), the permission ("used by permission:
  local use and AI viewing") as the licence text, and a `stone` field
  grouping photos of one stone (`a1`–`a3` are stone a), so no stone is split
  across tuning and test. The handle and the permission note go in a
  gitignored file.
- The photos have no EXIF, but each carries a Photoshop metadata block. They
  are copied into `references/library/` (gitignored) with all metadata
  stripped (`strip_metadata`); they never enter a commit, an artifact or an
  external service beyond the AI viewing the permission covers.
- Code changes: the open-licence check applies to tier 1 only; tier 2 needs a
  permission text; `library fetch` skips local entries; any future published
  weights or committed images use tier 1 only.
- Calipers give a mm scale on stones b, c and e (b3, e3 readable). The scale
  sits a few mm proud of the face, so a scale from it is approximate; it is
  recorded but not used in this ADR.

### 5. Tuning record (2026-10-29)

Built as `agatesim.specimen.rim.find_rim`; the split is fixed in
`references/rim-split.toml` (seed 73) and run with `scripts/rim_check.py`.
About 0.2 s per photo with cached patch features (0.6 s with the model),
about 90 MB peak. Changes from the literature, each tested on the 80 only:

- **Otsu split, not the mean.** With a large backdrop the eigenvector's
  mean lies near the backdrop's values, so patches next to the stone fell
  on its side (masks 1.7 times too large on synthetic stones).
- **τ = 0.6.** At 0.2 DINOv2's final tokens barely separate stone and
  backdrop; 0.4–0.6 give nearly the same results on the 80.
- **Backdrop colour near the edge.** Pixels within 1.5 patches of the
  patch mask's edge that match the frame's backdrop colours, and join it,
  are marked backdrop before the watershed. Deeper, it carved stone of the
  backdrop's colour (dark agate on black).
- **One piece.** A mask in pieces keeps its largest; a second piece nearly
  as large, or a neck that a small erosion cuts into two like pieces, means
  no single object.

Synthetic stones pass (IoU at least 0.97 plain, 0.91 on the others; the
background-only and frame-crossing controls give no outline). On the 80,
judged by helper agents: outlines on 43 of 59 photos with the rim in
frame (73%; bar 60%), 20 of 21 cut-off photos declined (95%; bar 90%), but
of the outlines judged, 28 of 36 follow the rim (**78%; bar 90%**). The
misses are mostly what colour and patch features can't settle: two halves
side by side read as one object, loops into the backdrop by stand clips,
a geode's inner cavity taken for its rim. A score from how much the pixels
inside and outside the outline look like the backdrop does not separate
good outlines from bad. The held-out set is untouched.

## Consequences

- Nodule can move its pin once the rim-finder passes, and recompute C1–C3
  and C6 on the photos where an outline is returned.
- The owner's time: one check of about 30 outlines.
- If B misses the bar, a follow-up ADR proposes C with its download and cost.
- `segment()`, the specimen server and the reference regression are
  unchanged.
