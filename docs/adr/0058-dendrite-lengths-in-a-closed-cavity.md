# 58. Dendrite lengths in a closed cavity

- Status: accepted
- Date: 2026-10-18
- Builds on: [ADR 0056](0056-dendrite-lattice-spacing-is-branch-width.md), [ADR 0057](0057-a-reproducible-gpu-dendrite-engine.md)

## Context

ADR 0057 found that the moss presets' dendrites don't follow Hou et al.'s
length law, N(L) ~ L^-1.25 [@hou2023]: their trees start 4 mm apart, so they
hardly compete for particles. The owner asked for a moss preset with closer
seeds, to test the law in a whole nodule.

## Study

`scripts/dendrite_length_law.py` fits the exponent α of N(≥L) ~ L^-α over the
longer half of the trees, and over the longest 10%, 100 and 50 of them. A
tree's length is how far it reaches from the surface it grew from.

| Forest | Trees | Median / longest | α: half | top 10% | top 100 | top 50 |
|---|---|---|---|---|---|---|
| Box 12 × 12 × 24 mm, from the floor, seeds 1 mm apart | 104 | 1.2 / 24 mm | 1.13 | 1.21 | 1.17 | 1.12 |
| Box 12 × 12 × 48 mm | 90 | 1.2 / 48 mm | 1.05 | 0.86 | 1.09 | 1.06 |
| Box 12 × 12 × 96 mm | 93 | 1.2 / 96 mm | 1.09 | 0.67 | 1.15 | 1.11 |
| `moss-3d` nodule, seeds 4 mm apart | 278 | 4.4 / 16.5 mm | 2.72 | 4.32 | 3.04 | 3.76 |
| `moss-dense-3d` nodule, seeds 1 mm apart | 2,863 | 1.0 / 16.9 mm | 1.70 | 2.27 | 2.96 | 4.03 |

(The box's top 10% is nine or ten trees.) Also measured: seeds 2 and 1.5 mm
apart in the nodule give α 2.0 and 1.8 over the longer half; more material at
1 mm (15–35% of the open space) merges the trees (1,900 → 100 separate ones);
a flat-walled cavity 24 mm wide gives 1.75, as the forests from opposite
walls meet halfway; every run used up its particles before the sweep limit.

## Findings

1. **From a flat surface into open space, the model gives Hou et al.'s law.**
   In the box, at every height, one tree runs ahead to the top and takes the
   particles from above it, and the rest stay short: screening competition,
   with α 1.1–1.3 over any range of the longer trees. Hou et al.'s dendrites
   grow from fracture surfaces into the rock's pores, a similar setting.
2. **In a closed nodule no tree can run ahead.** The cavity stops the longest
   trees short of its centre (about 17 mm in a 40 mm nodule), so the number of
   trees falls off steeply at the long end instead of as a power law. Closer
   seeds bring the longer half's exponent down (2.7 at 4 mm, 1.7 at 1 mm), but
   not to 1.25, and more material only merges the trees.
3. **So the model predicts** that dendrites inside a closed agate cavity do
   not follow the fracture-surface length law: their lengths are cut off by
   the cavity. That is a test for real moss agates, not a failure of the model;
   no source measuring dendrite lengths in agate cavities has been read.

## Decision

1. **Preset `moss-dense-3d`**: `moss-3d` with seeds 1 mm apart, the closest a
   closed cavity comes to the length law. It passes as moss agate on its
   configured cut (fractal dimension 1.46) and on 100% of 100 random cuts (512 px,
   seed 0).
2. Commit the study script; the moss presets are otherwise unchanged.

## Consequences

- Matching Hou et al.'s exponent needs an open setting, such as dendrites on a
  fracture face before the agate fills it; no agate form asks for that yet.
- Finding measurements of dendrite lengths in moss agate would test finding 3.
