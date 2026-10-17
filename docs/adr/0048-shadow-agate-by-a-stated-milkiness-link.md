# 48. Shadow agate by a stated milkiness link

- Status: accepted (owner decision, 2026-10-17)
- Date: 2026-10-17
- Amends: H1's rendering assumption ([ADR 0013](0013-mechanistic-front-feedback.md))
- Follows: [ADR 0035](0035-what-the-mechanistic-tier-requires.md), [ADR 0041](0041-reading-for-shadow-iris-and-plume.md) (and its amendment), [ADR 0045](0045-iris-no-longer-depends-on-shadow.md)

## Context

Shadow agate was the last form pending at the mechanistic tier. Its tests
judge milky and clear bands, so H1 needs a link from what it varies (the
impurity incorporated, the growth speed) to milkiness. Two time-boxed searches
found no source that makes that link (ADR 0041 and its amendment). The owner
decided to stop searching, state the link as an assumption, and proceed.

H1's link so far (ADR 0013) made translucency fall linearly with the
logarithm of the incorporated impurity, from 0.9 to 0.15 over the run's range.
Because H1's impurity rises and falls smoothly through each cycle, each band's
mean translucency differs little from its neighbours': on the shadow preset's
slab, alternation 0.43 (needs 0.6) and shadow sweep 0.25 (needs 0.3).

## Decision

1. **The link (an assumption, not sourced):** chalcedony is either milky
   (translucency 0.15) or clear (0.9). The fast, impurity-rich half of each
   cycle is milky, the slow, impurity-poor half clear, switching where H1
   already draws its band edges (the geometric midrange of the incorporated
   impurity). It is as if the fibre type changed with the band: H1's own
   description pairs trace-element-rich bands with twisted fibres
   ([@merino1995], as in ADR 0013). Which half is milky is unchanged from
   ADR 0013 (the owner chose to keep it, ADR 0045).
2. **It applies to every H1 result,** in 2D and 3D, not only to shadow
   (ADR 0035 rule 4: a link is not chosen form by form). Every H1 image now
   shows sharper milky/clear bands; the impurity stain is unchanged.
3. **Stated plainly:** this link was chosen after the graded one fell short
   of shadow's tests. Two simple links were tried, the graded one and this
   one; no thresholds were tuned. Shadow's verification rests on it, and the
   shadow renderer's optics are themselves a stated hypothesis (ADR 0010).
4. **Verification preset** `shadow-mechanistic`: the procedural shadow
   preset's cavity, seed and 2 mm slab, with H1 at its defaults.

## Results

- `shadow-mechanistic` passes at 768, 512, 384 and 256 px: alternation
  0.74–0.75 (≥ 0.6) over 35 bands, shadow sweep 0.49–0.52 (≥ 0.3).
- At 384 px it passes across H1's catalysis 17.4–80 (alternation 0.74–0.75,
  sweep 0.50–0.54).
- The same H1 run with the graded link fails both tests (0.43 and 0.25).
- No new criterion, so no new negative control; shadow's existing ones
  apply. A new test checks that H1's chalcedony takes only the two values and
  that milky pixels are exactly the more stained ones.
- Every other mechanistic verification still passes (the full suite): only
  the optical tests read translucency, and iris's gratings sit in the clear
  half, which is now fully clear.

## Consequences

- **Mechanistic tier: 12 of 12.** Every form is verified at both tiers.
- Shadow's mechanistic verification is the weakest of the twelve: it shows
  that H1 bands can make shadow agate *if* milkiness switches with the band
  as assumed. A source on what sets milkiness in chalcedony would test it.
- 2D regression hashes change for every H1 preset (translucency only);
  gallery images with H1 are regenerated.
