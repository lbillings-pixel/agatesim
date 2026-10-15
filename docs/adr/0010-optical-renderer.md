# 10. Optical renderer: shadow and iris agate

- Status: accepted
- Date: 2026-10-15

## Context

Shadow and iris agate are optical forms. Shadow agate is a sweep of shadows
across alternating clear and milky bands as the slab or the light moves. Iris
agate is rainbow colour in backlit thin slices from fine micro-banding. A
literature pass found the following:

- No peer-reviewed optical study of shadow agate.
- For iris: an iris band spacing of about 2 µm, micro-zonation at 0.5–5 µm, and
  iris zones in nearly every agate but often hidden by pigment
  ([@cartwright2026] §5.1.1, after [@jones1952]).

The owner chose a thin-slab model (bands continuing beneath the cut surface)
over waiting for full 3D (M9).

## Decision

1. **The slab as an optical object.** `RunConfig.optics` holds the slab
   thickness and how far the bands tilt from the slab normal beneath the cut. The
   formation models still describe only the cut surface. Material at depth z is
   the band deposited where growth had gone z·tan(tilt) farther: deposition time
   t + |∇t|·z·tan(tilt), looked up in a time-to-band table built from the fields.
   This uses scalar fields only, so there are no seams where opposite walls'
   bands meet.
2. **Shadow renderer** (`agatesim.optics.render_shadow`). It uses single
   scattering in reflected light:
   - Milky bands scatter strongly, clear bands weakly, and fine particles
     scatter blue more (Tyndall). Iron absorbs, blue most.
   - Light refracts at the surface (n = 1.54, assumed) and is tracked in a frame
     that moves with it, so each layer is sampled once.
   - Each uniform layer's contribution is integrated exactly, so results don't
     depend on the number of layers (checked).
   - The viewer looks straight down.
3. **Micro-banding field.** Fields gain `micro_spacing_um`: the spacing of
   regular micro-banding, NaN where it is irregular. The growth model gives a
   share `iris_fraction` of bands regular micro-bands with a log-normal spacing
   about `micro_band_um` (default 2 µm). These parameters are labelled
   *imposed*.
4. **Iris renderer** (`render_iris`). It shows a backlit thin slice seen off-axis.
   - Grating lines run along the visible bands. Order m appears at
     λ = d·sin θ_g / m, where θ_g is the deflection along the band normal, for
     orders 1–3.
   - Transmission falls with milkiness and pigment, so pigment conceals iris.
5. **Criteria.**
   - **shadow:**
     - `alternating-translucency`: mean change in translucency between
       consecutive bands of at least 0.6.
     - `angle-dependent-shadow`: within clear bands bounded by milky ones, the
       darkness centroid must move across the band by at least 0.3 of its
       width as the light swings between opposite directions. The shadow must
       be visible (contrast of at least 0.2) and sit on opposite sides for
       opposite light at every angle. A linear fit to the angle was tried and
       rejected: the shadow position saturates at steep angles.
   - **iris:**
     - `grating-spacing`: median visible micro-band spacing of 0.5–5 µm.
     - `spectral-dispersion`: the median difference between the hue wavelength
       of the rendered colour and the first-order prediction must be at most
       15 nm. This is a check on the renderer itself. Its negative controls
       inject broken renderers (white light, wrong angle).
6. **Live optical views.** `POST /api/optics` renders the preview in shadow or
   iris light at a given angle. Recent simulations are cached, so moving the
   angle slider doesn't re-simulate.

## Consequences

- All twelve archetypes now have criteria, and all are verified at the
  procedural tier.
- Simplifications to revisit:
  - The shadow model is a hypothesis, not a sourced mechanism. Its coefficients
    are effective values, and n = 1.54 is still to source.
  - With strongly tilted bands, a slab looks milky everywhere (milky material
    under every clear band), and oblique light crossing many bands per layer can
    alias. Shadow presets use bands that run straight down.
  - Iris is rendered as an ideal thin grating (orders 1–3, intensity ∝ 1/m²),
    with no model of the actual refractive-index contrast.
  - Optical views are reflected or transmitted light at one angle at a time. Full
    3D light transport belongs to M9.
