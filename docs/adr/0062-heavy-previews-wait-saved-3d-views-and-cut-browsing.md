# 62. Heavy previews wait; saved 3D views; browsing random cuts; Reset

- Status: accepted (owner choices, 2026-10-23)
- Date: 2026-10-23
- Builds on: [ADR 0021](0021-three-dimensional-runs.md), [ADR 0060](0060-a-caution-badge-for-heavy-actions.md)

## Context

The owner tried the app at the desktop and reported four things:

- **A.** 3D runs can be saved at higher resolutions, but there was no clear way
  to see them. Opening a saved run only loaded its settings and recomputed a
  preview-sized view; its saved fields were never read.
- **B.** A random-cut survey computes and judges every cut, but showed only
  the summary table, never the cuts themselves.
- **C.** Some actions started heavy work with no warning first. Choosing H2
  (Liesegang) on the 3D screen began a formation estimated at about 4 minutes
  and 4.6 GB. The caution badge (ADR 0060) appeared beside work that had
  already started. The 2D preview and the "Two ways" screen also start
  previews by themselves.
- **D.** After Randomize it was hard to tell what had changed, and there was no
  single way back.

## Decision

The owner chose each option below.

1. **Heavy previews wait for a press of Build.** Before an automatic preview
   starts (the 2D live preview, the 3D view and its cut, each preview on the
   "Two ways" screen), the app asks for the estimate. If it is heavy (over 30 s
   or 2 GB, ADR 0060), the app shows the estimate and its reasons with a
   **Build it** button instead of starting. Light previews still update by
   themselves. A press applies to that configuration (the 2D screen) or that
   formation (the 3D screen), so moving the cut never asks again. If the
   estimate fails, the preview builds as before. The 2D estimate now knows its
   own cache, as the 3D one already did: a preview already simulated costs
   nothing again. Shadow and iris views wait for the preview, so they cannot
   build a paused preview behind its back.
2. **Opening a saved 3D run shows its saved volume.**
   `GET /api/volume/runs/{id}/voxels` reads `fields.zarr`, a slab of z-layers
   at a time, and sends the same bytes as the live view. A run larger than
   256 voxels along a side sends every stride-th voxel, and the screen says
   which. The read colours voxels with the live view's own function, and a
   test checks that saved and live bytes are identical. A banner names the
   run and leads back to the live view. Changing anything except the cut
   returns to the live view. The cut itself is always computed from the
   model, which works at any resolution, so it is the same cut the run saved.
   The run's saved random-cut results show beside it. The live 3D view also
   goes up to 192³ now, with the caution badge.
3. **Random cuts can be browsed.** The survey keeps a 160 px picture of each
   cut it makes, through a callback, so the model layer stays free of
   rendering. The pictures come back with each cut's plane and verdict. They
   show as a grid that can be filtered to all, passing or failing cuts.
   Choosing one loads it as the main cut at full detail, judged test by test.
   A 20-cut survey took 4.7 s with the pictures. The pictures are not saved
   with full runs: their surveys list the cuts as text, and each one still
   opens as the main cut.
4. **Reset returns to the settings last loaded:** a preset, a form, a run, a
   "Two ways" version or a specimen replica. It is undoable. Its label counts
   the settings that differ, and its tooltip names them.

## Consequences

- A heavy preview now costs one press. In return, nothing heavy starts
  unannounced, which matters most when the app is used from a phone.
- Saved runs are viewable at their full resolution up to 256³. Larger ones
  (up to 384³) are shown thinned out, and the screen says so.
- Survey responses are larger: about 5 to 15 KB per cut picture, so about
  1 MB for 100 cuts.
