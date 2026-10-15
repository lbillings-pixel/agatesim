# Roadmap

Milestones end with a check-in: results, images, and the next decisions.

| Milestone | Scope | Status |
|---|---|---|
| **M0: Foundation** | Repository layout, ADRs, archetype registry (12 forms, all pending), reference catalogue, science notes draft, CI | done |
| **M1: First procedural models** | 2D grid and exact cavity geometry; 9 preset cavity shapes (volcanic, sedimentary, seam); run config and records; procedural fortification, seam and waterline, verified with negative controls; `agatesim run` CLI; PNG output | done |
| **M2: Web UI v1** | Rendering touch-up; 14 openly licensed specimen photos; FastAPI backend; React app with parameter panel, preset shape menu, live preview, background runs, run browser, slab viewer with growth slider and comparison | done |
| **M3: Schedules and the combined form** | Formation time and schedules (timeline editor in the UI); procedural growth model; combined fortification–waterline (both stage orders); quartz-centre geode; band-statistics module with run comparison ([ADR 0007](adr/0007-formation-history-and-growth-model.md)) | done |
| **M4: Drawing tool and nucleation** | Cavity drawing tool (corners or freehand, angular or smooth); tubes placed by clicking; spherulitic growth from nucleation sites → botryoidal, eye; tube agate; quartz crystals with pointed growth forms that coarsen by geometric selection ([ADR 0008](adr/0008-drawn-cavities-nucleation-and-crystal-growth.md)) | done |
| **M5: Dendrites** | Diffusion-limited growth → moss, plume | next |
| **M6: Optical renderer** | Translucency and colour → shadow; wave optics → iris | |
| **M7: Specimen analysis I** | Photo upload and scale; outline tracing; observed fields from photos; identify forms with the archetype criteria; fit procedural parameters; replica side by side ([ADR 0006](adr/0006-specimen-photo-analysis.md)) | |
| **M8: Mechanistic models** | Reaction–diffusion / phase-field (H2), front feedback (H1), settling (H4); GPU backend | |
| **M9: 3D** | Volumetric runs, slicing in the viewer | |
| **M10: Specimen analysis II** | Simulation-based inference of mechanistic conditions from photos, with uncertainty | |
