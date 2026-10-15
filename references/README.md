# References

## Literature: `catalogue.toml`

Every literature source the project relies on, with:

- **how far it has been checked:** citation, abstract, or full text. The docs never
  claim more than that.
- **its licence.** Only material whose licence allows it (for example CC BY) is
  stored in this repository. Everything else is cited and linked.

Docs cite entries as `[@id]`. The test suite checks that every citation resolves.

## Specimen photos: `images/`

Openly licensed photos of real agates, from Wikimedia Commons, stored with
attribution in `images/catalogue.toml` (author, licence, source page). Each entry
records:

- which archetypes the photo shows, as reviewed by eye;
- whether it is a cut slab or a rough surface;
- whether it is **analysis-ready**: flat, face-on and unobstructed, so it can serve
  as a test input for photo analysis (ADR 0006).

The licences (CC BY and CC BY-SA, various versions) apply to the image files and
anything derived from them. They don't affect the MIT licence of the code. When
reusing an image, credit its author and licence as listed.

| Form | Photos | Analysis-ready |
|---|---:|---:|
| fortification | 6 | 4 |
| seam | 1 | 1 |
| waterline | 3 | 2 |
| fortification-waterline | 3 | 2 |
| quartz-geode | 3 | 1 |
| botryoidal | 4 | 2 |
| eye | 2 | 2 |
| tube | 0 | 0 |
| moss | 1 | 1 |
| plume | 1 | 1 |
| shadow | 1 | 0 |
| iris | 1 | 0 |

Gaps to fill: tube agate, and more analysis-ready seams, eyes and optical forms.
