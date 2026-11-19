"""The crystals' closed form for GPU code (ADR 0090).

`CRYSTAL_TIME_CUDA` is CUDA source for programs that include it (a renderer
drawing the hollow left by a run's quartz crystals). It holds device functions
only, no kernels, and no CuPy is needed to import it. They give the time for one
crystal to reach a point, as `Crystals.pair_times` does, and its gradient (the
wall's normal direction where that crystal is the earliest).

A crystal is one row of `CrystalWall.packed()`: site x, y, z, then the unit long
axis x, y, z. The stage's shared numbers come from `shape_numbers`. With along
the offset from the site along the axis and across its distance from the axis:

    tip  = |along| + across · cot(alpha)
    side = across · elongation               (elongation = 1 / side_rate)
    time = max(tip, side)

`across` is taken from the offset less its part along the axis, not from
|offset|² − along², which in float32 loses about sqrt(eps)·|offset| near the axis.
On a tie the tip's gradient is returned; on the axis (across 0) the across
term's gradient is taken as 0, and at along 0 the axis term's sign as +.
"""

from __future__ import annotations

import math

from agatesim.volume.growth import CrystalWall

ROW = 6  # numbers per crystal in CrystalWall.packed()

CRYSTAL_TIME_CUDA = r"""
// agatesim ADR 0090: one crystal's arrival time at a point and its gradient.
// c points to the crystal's row: site x, y, z, unit axis x, y, z.
// cot_alpha = cot(tip half-angle); elongation = 1 / side rate.
// g (may be null) receives the gradient of the time at the point.
template <typename T>
__device__ __forceinline__ T agatesim_crystal_time_grad(
    T px, T py, T pz, const T* __restrict__ c, T cot_alpha, T elongation, T* g)
{
    const T ox = px - c[0], oy = py - c[1], oz = pz - c[2];
    const T ax = c[3], ay = c[4], az = c[5];
    const T along = ox * ax + oy * ay + oz * az;
    const T qx = ox - along * ax, qy = oy - along * ay, qz = oz - along * az;
    const T across = sqrt(qx * qx + qy * qy + qz * qz);
    const T tip = fabs(along) + across * cot_alpha;
    const T side = across * elongation;
    const bool on_tip = tip >= side;
    if (g) {
        const T s = on_tip ? (along < T(0) ? T(-1) : T(1)) : T(0);
        const T k = across > T(0) ? (on_tip ? cot_alpha : elongation) / across : T(0);
        g[0] = s * ax + k * qx;
        g[1] = s * ay + k * qy;
        g[2] = s * az + k * qz;
    }
    return on_tip ? tip : side;
}

template <typename T>
__device__ __forceinline__ T agatesim_crystal_time(
    T px, T py, T pz, const T* __restrict__ c, T cot_alpha, T elongation)
{
    return agatesim_crystal_time_grad<T>(px, py, pz, c, cot_alpha, elongation, (T*)0);
}
"""


def shape_numbers(wall: CrystalWall) -> tuple[float, float]:
    """(cot_alpha, elongation): the stage's shared numbers the device functions take."""
    return 1.0 / math.tan(wall.alpha), 1.0 / wall.side_rate
