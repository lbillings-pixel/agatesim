# 11. Specimen photo analysis, first pass

- Status: accepted
- Date: 2026-10-15
- Builds on: [ADR 0006](0006-specimen-photo-analysis.md)

## Context

ADR 0006 planned photo upload with a scale, outline tracing, observed fields, form
identification with the archetype criteria, a fitted replica, and a side-by-side
view. The owner supplied eight photos of their own specimens: two polished
Brazilian slabs and six wet, sawn half-nodules from Hebei, on a blue cloth, with
an inch ruler, under room light plus a flashlight. Those photos showed what the
analysis must cope with:

- strong cast shadows and a flashlight hot spot;
- glare on wet and polished faces;
- a ruler lying below the cut face (about 11% scale error for a 22 mm slab, from
  the 26 mm-equivalent lens about 21–24 cm up);
- GPS coordinates in every file's metadata.

## Decision

1. **Privacy.** Photos stay in a gitignored folder (`specimens/`). The app serves
   them only as PNGs written fresh from pixel arrays, so no metadata leaves with
   them. Only the 35 mm-equivalent focal length is read from the metadata. The
   repository's tests use synthetic photos only.
2. **Scale.** The user clicks two points on the ruler and enters their distance
   (inches or mm) and how far the cut face stands above the ruler. A camera at
   height D sees the face h higher magnified by D / (D − h). D follows from the
   ruler scale and the focal length.
3. **Segmentation.** A marker-based watershed on the colour gradient.
   - Background markers: the image border, the cloth-coloured areas connected
     to it (judged by brightness-free "blue excess"), shadows connected to the
     cloth, and long objects such as the ruler.
   - Specimen marker: the most compact central object, eroded until it separates
     from a ruler it touches. The user can click the specimen instead.
   - Dark voids enclosed by the specimen stay part of it. This succeeded on all
     eight owner photos.
4. **Observed fields.** The face is resampled onto a simulation grid in
   millimetres, with the traced outline as a drawn cavity.
   - Lighting is flattened by dividing out a quadratic illumination surface.
   - Colours are grouped into six classes (k-means), majority-filtered, and
     slivers removed. Each connected patch is a band piece. Pieces of the same
     class at about the same depth are joined into one band, and bands are
     numbered inward by depth.
   - Deposition time is the band rank, smoothed. Translucency comes from
     brightness and iron from warmth. Open space is dark relative to the face's
     bright material.
   - Quartz is **not** detected: a brightness-and-texture rule took milky bands
     for quartz in validation.
5. **Validation on synthetic photos.** Verification presets are rendered,
   pasted onto a lit cloth with a shadow, noise and a ruler, and saved at JPEG
   quality 95 and 75 with two noise seeds. The analysis is then compared with
   the truth (28 photos):
   - segmentation is within 12% of the true face area (within 5% for most);
   - band thickness is within 50% where bands are wide enough;
   - verdicts: for six forms there were **no false positives**, but forms
     present were rarely confirmed (0–1 of 4). Eye had 7 false positives.

   So a photo *pass* is reported as "confirmed" only for those six forms; eye
   passes are "possible (unreliable test)"; a fail is "not confirmed", which says
   little. A test guards the no-false-positive claim. Criterion values are
   always shown as measurements.
6. **Replica.** The growth model, run in the specimen's own outline. A first
   guess comes from the observed statistics (lining depth from the open share,
   band period from thickness, variability from the thickness spread, contrast,
   iron), then a small seeded search refines it. A replica is a procedural
   likeness, not a reconstruction of how the specimen formed (ADR 0005).
7. **App.** A Specimens screen:
   - pick or upload a photo, mark the ruler, give the face height, host and
     which way was up;
   - Analyse shows the traced outline, a false-colour band map and the forms
     table;
   - Replicate shows the replica, and "open in the simulator" loads it.

## Consequences

- Photos can be measured and replicated, but forms are seldom *confirmed* from a
  photo yet. The bottleneck is band tracing: real and synthetic bands break
  into pieces where colour shifts along them, and the strict criteria (closed
  rings, the worst band's flatness) fail on the pieces.
- Photo verdicts were validated only on synthetic slabs at about 760 px across;
  smaller or heavily compressed photos are less reliable.
- Next steps (folded into M10 unless promoted earlier):
  - trace bands as continuous contours along the band-orientation field, rather
    than as colour patches;
  - order horizontal bands by height;
  - detect quartz, voids and inclusions properly;
  - replicas with waterline floors when horizontal bands are found;
  - a robustness score per criterion for photos.
