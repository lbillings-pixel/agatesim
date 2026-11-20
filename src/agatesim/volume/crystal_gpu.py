"""The crystals' closed form for GPU code (ADR 0090, ADR 0092).

`CRYSTAL_TIME_CUDA` is CUDA source for programs that include it (a renderer
drawing the hollow left by a run's quartz crystals). It holds device functions
only, no kernels, and no CuPy is needed to import it. They give the time for one
crystal to reach a point, as `Crystals.pair_times` does, and its gradient (the
wall's normal direction where that crystal is the earliest).

A crystal is one row of `CrystalWall.packed()` (ROW numbers, also defined in the
source as AGATESIM_CRYSTAL_ROW): site x, y, z, the unit long axis x, y, z, then
the unit normal of its first face across the axis x, y, z (zeros when round).
The stage's shared numbers come from `shape_numbers`. With along the offset from
the site along the axis and q its part across the axis:

    across = |q|                                   (faces 0: round)
           = q . f, f the nearest face normal      (faces n >= 3; ADR 0092)
    tip    = |along| + across · cot(alpha)
    side   = across · elongation                   (elongation = 1 / side_rate)
    time   = max(tip, side)

The nearest face normal lies at a whole multiple of 360/n degrees from the
first face's, about the axis: the one q projects on most. The device steps round
the normals (cos and sin of k 360/n by rotation; exact constants for six faces)
and takes no angle, quicker than atan2, sin and cos; `Crystals.across` takes
the angle, and the two pick the same face up to ties, where the projections are
equal. `across` is taken from q, not from |offset|² − along², which in float32 loses
about sqrt(eps)·|offset| near the axis. On a tie the tip's gradient is returned;
on the axis (q 0) the across term's gradient is taken as 0, and at along 0 the
axis term's sign as +.
"""

from __future__ import annotations

import math

from agatesim.volume.growth import CrystalWall

ROW = 9  # numbers per crystal in CrystalWall.packed()

CRYSTAL_TIME_CUDA = r"""
// agatesim ADR 0090, 0092: one crystal's arrival time at a point and its gradient.
// c points to the crystal's row: site x, y, z, unit axis x, y, z, first face normal
// x, y, z (zeros when round). cot_alpha = cot(tip half-angle); elongation = 1 / side
// rate; faces = 0 (round) or n >= 3 faces round the axis.
// g (may be null) receives the gradient of the time at the point.
#define AGATESIM_CRYSTAL_ROW 9
template <typename T>
__device__ __forceinline__ T agatesim_crystal_time_grad(
    T px, T py, T pz, const T* __restrict__ c, T cot_alpha, T elongation, int faces, T* g)
{
    const T ox = px - c[0], oy = py - c[1], oz = pz - c[2];
    const T ax = c[3], ay = c[4], az = c[5];
    const T along = ox * ax + oy * ay + oz * az;
    const T qx = ox - along * ax, qy = oy - along * ay, qz = oz - along * az;
    const T r = sqrt(qx * qx + qy * qy + qz * qz);
    // the across term and the unit direction of its gradient
    T across = r, dx = T(0), dy = T(0), dz = T(0);
    if (r > T(0)) {
        if (faces > 0) {
            const T ux = c[6], uy = c[7], uz = c[8];
            const T wx = ay * uz - az * uy, wy = az * ux - ax * uz, wz = ax * uy - ay * ux;
            const T qu = qx * ux + qy * uy + qz * uz, qw = qx * wx + qy * wy + qz * wz;
            // the nearest face normal is the one q projects on most: step round the faces'
            // normals (cos, sin of k sector), no angle taken (six faces: exact constants)
            T cs = T(0.5), ss = T(0.8660254037844386);
            if (faces != 6) {
                const T sector = T(6.283185307179586) / T(faces);
                cs = cos(sector);
                ss = sin(sector);
            }
            T ck = T(1), sk = T(0), ct = T(1), st = T(0);
            across = qu;
            for (int k = 1; k < faces; ++k) {
                const T cn = ck * cs - sk * ss;
                sk = sk * cs + ck * ss;
                ck = cn;
                const T p = qu * ck + qw * sk;
                if (p > across) { across = p; ct = ck; st = sk; }
            }
            dx = ct * ux + st * wx;
            dy = ct * uy + st * wy;
            dz = ct * uz + st * wz;
        } else {
            dx = qx / r;
            dy = qy / r;
            dz = qz / r;
        }
    }
    const T tip = fabs(along) + across * cot_alpha;
    const T side = across * elongation;
    const bool on_tip = tip >= side;
    if (g) {
        const T s = on_tip ? (along < T(0) ? T(-1) : T(1)) : T(0);
        const T k = on_tip ? cot_alpha : elongation;
        g[0] = s * ax + k * dx;
        g[1] = s * ay + k * dy;
        g[2] = s * az + k * dz;
    }
    return on_tip ? tip : side;
}

template <typename T>
__device__ __forceinline__ T agatesim_crystal_time(
    T px, T py, T pz, const T* __restrict__ c, T cot_alpha, T elongation, int faces)
{
    return agatesim_crystal_time_grad<T>(px, py, pz, c, cot_alpha, elongation, faces, (T*)0);
}
"""


def shape_numbers(wall: CrystalWall) -> tuple[float, float, int]:
    """(cot_alpha, elongation, faces): the stage's shared numbers the device
    functions take."""
    return 1.0 / math.tan(wall.alpha), 1.0 / wall.side_rate, wall.faces
