# References

## Literature: `catalogue.toml`

Every literature source the project relies on, with:

- **how far it has been checked:** citation, abstract, named sections, or full text. The docs never
  claim more than that.
- **its licence.** Only material whose licence allows it (for example CC BY) is
  stored in this repository. Everything else is cited and linked.

Docs cite entries as `[@id]`. The test suite checks that every citation resolves.

## Specimen photos: `images/`

Openly licensed photos of real agates, from Wikimedia Commons, stored with
attribution in `images/catalogue.toml` (author, licence, source page). Each entry
records:

- which archetypes the photo shows, as reviewed by eye;
- whether it is a cut slab or a rough surface.

Whether a photo is fit for analysis is measured by the quality gate (ADR 0064),
not set by hand; `tests/data/reference_regression.json` records the result for
each photo (ADR 0066).

The licences (CC BY and CC BY-SA, various versions) apply to the image files and
anything derived from them. They don't affect the MIT licence of the code. When
reusing an image, credit its author and licence as listed.

## Reference library: `library*.toml`

A larger set of photos for classification and calibration (ADR 0063, 0066). The
images aren't stored here: `agatesim library fetch` downloads them into
`references/library/` (gitignored). Labels describe appearance only, never
evidence for a formation mechanism.

| File | Holds | Written by |
|---|---|---|
| `library.toml` | the photo list: source, author, licence, and guessed forms (not labels) | `scripts/build_library.py` |
| `library-labels.toml` | forms labelled by eye | the Reference labels screen |
| `library-taps.toml` | test taps for the feature maps (ADR 0068), never used for training | the screen's tap mode |
| `library-train-taps.toml` | training taps for the feature maps (ADR 0070) | the screen's tap mode |
| `rim-split.toml` | the rim finder's tuning, held-out and hard test sets (ADR 0073) | `scripts/rim_check.py` |
