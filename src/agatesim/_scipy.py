"""Typed wrappers around the scipy functions we use.

scipy ships incomplete type information, so calls are isolated here and the
rest of the package stays under strict type checking.
"""
# pyright: basic

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage, sparse, special
from scipy.integrate import solve_ivp
from scipy.sparse import linalg as sparse_linalg
from scipy.spatial import ConvexHull, KDTree

from agatesim.grid import FloatArray

FOUR_CONNECTED = ndimage.generate_binary_structure(2, 1)
EIGHT_CONNECTED = ndimage.generate_binary_structure(2, 2)


def nearest_distance(samples: FloatArray, points: FloatArray) -> NDArray[np.float64]:
    """Distance from each of `points` (n, 2) to the nearest of `samples` (m, 2)."""
    result: Any = KDTree(samples).query(points, workers=-1)
    return cast(NDArray[np.float64], result[0])


class NearestIndex:
    """A k-d tree over sample points, for repeated nearest-sample queries."""

    def __init__(self, samples: FloatArray) -> None:
        self._tree = KDTree(samples)

    def query(self, points: FloatArray) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
        """Distance to, and index of, the nearest sample for each point."""
        result: Any = self._tree.query(points, workers=-1)
        return (
            np.asarray(result[0], dtype=np.float64),
            np.asarray(result[1], dtype=np.int64),
        )

    def query_k(self, points: FloatArray, k: int) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
        """Distances to, and indices of, the k nearest samples, shaped (n, k)."""
        result: Any = self._tree.query(points, k=k, workers=-1)
        return (
            np.asarray(result[0], dtype=np.float64).reshape(len(points), k),
            np.asarray(result[1], dtype=np.int64).reshape(len(points), k),
        )


def distance_to_false(mask: NDArray[np.bool_], dx: float) -> NDArray[np.float64]:
    """Distance (in units of dx) from each True pixel centre to the nearest False pixel centre."""
    return cast(NDArray[np.float64], ndimage.distance_transform_edt(mask, sampling=dx))


def nearest_index(samples: FloatArray, points: FloatArray) -> NDArray[np.int64]:
    """Index of the nearest of `samples` (m, 2) for each of `points` (n, 2)."""
    result: Any = KDTree(samples).query(points, workers=-1)
    return cast(NDArray[np.int64], result[1])


def nearest_true_indices(mask: NDArray[np.bool_]) -> NDArray[np.int64]:
    """For every pixel, the (row, col) index of the nearest True pixel; shape (2, ny, nx)."""
    result: Any = ndimage.distance_transform_edt(~mask, return_indices=True)
    return cast(NDArray[np.int64], result[1])


def gaussian(field: FloatArray, sigma: float, *, wrap: bool = False) -> NDArray[np.float64]:
    """Gaussian blur. `wrap` treats the field as periodic, for smoothing noise
    without edge artefacts."""
    mode = "wrap" if wrap else "nearest"
    return cast(NDArray[np.float64], ndimage.gaussian_filter(field, sigma=sigma, mode=mode))


def bilinear(field: FloatArray, rows: FloatArray, cols: FloatArray):
    """Sample `field` at fractional (row, col) positions by bilinear interpolation."""
    out = ndimage.map_coordinates(field, [rows, cols], order=1, mode="nearest")
    return cast(NDArray[np.float64], out)


def linear_at(field: FloatArray, coords: list[FloatArray]) -> NDArray[np.float64]:
    """Sample an n-dimensional `field` at fractional indices (one array per axis) by
    linear interpolation."""
    out = ndimage.map_coordinates(field, coords, order=1, mode="nearest")
    return cast(NDArray[np.float64], out)


def hull_planes(points: FloatArray) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """The convex hull of 3D points as planes n·x ≤ b with unit outward normals n,
    one per face (coplanar triangles merged)."""
    equations = np.asarray(ConvexHull(points).equations, dtype=np.float64)  # n·x + c ≤ 0
    unique = np.unique(np.round(equations, 9), axis=0)
    return unique[:, :3], -unique[:, 3]


def count_components(mask: NDArray[np.bool_], *, eight_connected: bool) -> int:
    structure = EIGHT_CONNECTED if eight_connected else FOUR_CONNECTED
    result: Any = ndimage.label(mask, structure=structure)
    return int(result[1])


def erode(mask: NDArray[np.bool_], iterations: int) -> NDArray[np.bool_]:
    out = ndimage.binary_erosion(mask, structure=FOUR_CONNECTED, iterations=iterations)
    return cast(NDArray[np.bool_], out)


def rim_3d(inside: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """Inside cells of a 3D mask with an outside cell among their 26 neighbours."""
    interior: Any = ndimage.binary_erosion(inside, structure=np.ones((3, 3, 3), dtype=bool))
    return inside & ~cast(NDArray[np.bool_], interior)


def normal_quantile(u: FloatArray) -> NDArray[np.float64]:
    """Standard normal quantiles of uniform draws (clipped away from 0 and 1)."""
    return cast(NDArray[np.float64], special.ndtri(np.clip(u, 1e-12, 1 - 1e-12)))


def label(mask: NDArray[np.bool_], *, eight_connected: bool) -> NDArray[np.int32]:
    """Connected-component labels (0 = background, 1..n = components)."""
    structure = EIGHT_CONNECTED if eight_connected else FOUR_CONNECTED
    result: Any = ndimage.label(mask, structure=structure)
    return cast(NDArray[np.int32], result[0])


def local_maxima(field: FloatArray, size: int) -> NDArray[np.bool_]:
    """Pixels equal to the maximum of their size x size neighbourhood."""
    peak = ndimage.maximum_filter(field, size=size, mode="constant", cval=-np.inf)
    return cast(NDArray[np.bool_], field == peak)


def open_close(mask: NDArray[np.bool_], iterations: int) -> NDArray[np.bool_]:
    """Morphological opening then closing (removes specks, then fills small gaps)."""
    opened = ndimage.binary_opening(mask, structure=FOUR_CONNECTED, iterations=iterations)
    closed = ndimage.binary_closing(opened, structure=FOUR_CONNECTED, iterations=iterations)
    return cast(NDArray[np.bool_], closed)


def fill_holes(mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
    return cast(NDArray[np.bool_], ndimage.binary_fill_holes(mask))


def dilate(mask: NDArray[np.bool_], iterations: int) -> NDArray[np.bool_]:
    out = ndimage.binary_dilation(mask, structure=FOUR_CONNECTED, iterations=iterations)
    return cast(NDArray[np.bool_], out)


def uniform(field: FloatArray, size: int) -> NDArray[np.float64]:
    """Mean over a size × size window."""
    return cast(NDArray[np.float64], ndimage.uniform_filter(field, size=size))


def close_1d(profile: NDArray[np.bool_], length: int) -> NDArray[np.bool_]:
    """1D morphological closing: bridges False gaps shorter than `length`. The
    profile is padded first, so a run touching an end isn't eroded there."""
    pad = length
    padded = np.pad(profile, pad, mode="edge")
    out = ndimage.binary_closing(padded, structure=np.ones(length, dtype=bool))
    return cast(NDArray[np.bool_], out[pad:-pad])


def runs(profile: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """(start, stop) of each run of True in a 1D profile."""
    lab, n = cast(tuple[NDArray[np.int32], int], ndimage.label(profile))
    out: list[tuple[int, int]] = []
    for k in range(1, n + 1):
        idx = np.flatnonzero(lab == k)
        out.append((int(idx[0]), int(idx[-1]) + 1))
    return out


def median_1d(values: FloatArray, size: int) -> NDArray[np.float64]:
    return cast(NDArray[np.float64], ndimage.median_filter(values, size=size, mode="nearest"))


def gaussian_rgb(rgb: NDArray[np.generic], sigma: float) -> NDArray[np.float64]:
    """Gaussian blur of each colour channel."""
    x = np.asarray(rgb, dtype=np.float64)
    return np.stack([ndimage.gaussian_filter(x[..., c], sigma) for c in range(x.shape[-1])], -1)


def colour_gradient(rgb: NDArray[np.generic], sigma: float) -> NDArray[np.uint16]:
    """Gradient magnitude summed over colour channels, scaled to uint16."""
    x = gaussian_rgb(rgb, sigma)
    g = np.zeros(x.shape[:2])
    for c in range(x.shape[-1]):
        g += np.hypot(ndimage.sobel(x[..., c], axis=0), ndimage.sobel(x[..., c], axis=1))
    g = g / max(float(g.max()), 1e-9) * 65535
    return g.astype(np.uint16)


def watershed(gradient: NDArray[np.uint16], markers: NDArray[np.int16]) -> NDArray[np.int16]:
    """Marker-based watershed (image foresting transform)."""
    return cast(NDArray[np.int16], ndimage.watershed_ift(gradient, markers.astype(np.int16)))


def majority(labels: NDArray[np.int32], passes: int) -> NDArray[np.int32]:
    """Replace each label by the most common label in its 3x3 neighbourhood
    (labels -1 are left alone and never spread)."""
    out = labels.copy()
    k = int(labels.max()) + 1
    if k <= 0:
        return out
    for _ in range(passes):
        counts = np.stack(
            [ndimage.uniform_filter((out == i).astype(np.float64), size=3) for i in range(k)]
        )
        winner = np.argmax(counts, axis=0).astype(np.int32)
        out = np.where(labels >= 0, winner, labels)
    return out


def solve_anisotropic(
    region: NDArray[np.bool_],
    d11: FloatArray,
    d22: FloatArray,
    d12: FloatArray,
    zero: NDArray[np.bool_],
    one: NDArray[np.bool_],
    colour: FloatArray | None = None,
    contrast: float = 1.0,
) -> NDArray[np.float64]:
    """Solve div(D grad u) = 0 on `region`, D = [[d11, d12], [d12, d22]] per pixel
    (x along columns, y along rows), with u = 0 on `zero`, u = 1 on `one` and no
    flux across the region's other edges; NaN outside.

    Conservative finite volumes: the flux through each face between two pixels
    uses the face-averaged D, with the cross term from the four pixels beside the
    face (a pixel outside the region is replaced by its neighbour on the face, a
    one-sided difference). With `colour`, a face's flux is scaled by
    exp(-(colour difference / contrast)^2), floored at 1%, so pixels that look
    different hardly exchange. Not monotone, so the result is clipped to [0, 1]."""
    h, w = region.shape
    out = np.full((h, w), np.nan)
    rows_in, cols_in = np.nonzero(region)
    n = len(rows_in)
    if n == 0 or not (one & region).any() or not (zero & region).any():
        return out
    index = np.full((h + 2, w + 2), -1, dtype=np.int64)  # padded: no bounds checks
    index[rows_in + 1, cols_in + 1] = np.arange(n)

    def at(dr: int, dc: int, r: NDArray[np.intp], c: NDArray[np.intp]) -> NDArray[np.int64]:
        return index[r + 1 + dr, c + 1 + dc]

    entries_r: list[NDArray[np.int64]] = []
    entries_c: list[NDArray[np.int64]] = []
    entries_v: list[NDArray[np.float64]] = []
    for dr, dc in ((0, 1), (1, 0)):  # east faces, south faces
        q = at(dr, dc, rows_in, cols_in)
        ok = q >= 0
        p = np.flatnonzero(ok)
        q = q[ok]
        r, c = rows_in[ok], cols_in[ok]
        r2, c2 = r + dr, c + dc
        normal = d11 if dc else d22
        k_n = 0.5 * (normal[r, c] + normal[r2, c2])
        k_x = 0.25 * 0.5 * (d12[r, c] + d12[r2, c2])
        # Pixels beside the face, on the side of p and of q (for the cross term):
        # along the other axis, + then -.
        sr, sc = (1, 0) if dc else (0, 1)
        side = []
        for sign in (1, -1):
            for base, (br, bc) in ((p, (r, c)), (q, (r2, c2))):
                beside = at(sign * sr, sign * sc, br, bc)
                side.append((np.where(beside >= 0, beside, base), sign))
        scale = np.ones(len(p))
        if colour is not None:
            diff = np.linalg.norm(colour[r, c] - colour[r2, c2], axis=-1)
            scale = np.maximum(np.exp(-((diff / contrast) ** 2)), 0.01)
        # Flux F = scale * (k_n (u_q - u_p) + k_x * sum(sign * u_side)).
        terms = [(q, k_n), (p, -k_n), *((s, sign * k_x) for s, sign in side)]
        for target, coef in terms:
            for row, sgn in ((p, 1.0), (q, -1.0)):  # F leaves p, enters q
                entries_r.append(row)
                entries_c.append(target)
                entries_v.append(sgn * scale * coef)
    rr = np.concatenate(entries_r)
    cc = np.concatenate(entries_c)
    vv = np.concatenate(entries_v)
    fixed = (zero | one)[rows_in, cols_in]
    value = one[rows_in, cols_in].astype(np.float64)
    free_row = ~fixed[rr]
    to_fixed = fixed[cc]
    rhs = np.zeros(n)
    np.add.at(
        rhs, rr[free_row & to_fixed], -vv[free_row & to_fixed] * value[cc[free_row & to_fixed]]
    )
    keep = free_row & ~to_fixed
    fixed_ids = np.flatnonzero(fixed)
    rhs[fixed_ids] = value[fixed_ids]
    matrix = sparse.coo_matrix(
        (
            np.concatenate([vv[keep], np.ones(len(fixed_ids))]),
            (np.concatenate([rr[keep], fixed_ids]), np.concatenate([cc[keep], fixed_ids])),
        ),
        shape=(n, n),
    ).tocsr()
    # A pocket cut off from both ends is singular; a tiny pull to 0 keeps it solvable.
    matrix = matrix - sparse.diags(np.where(fixed, 0.0, 1e-9))
    solution = np.asarray(sparse_linalg.spsolve(matrix, rhs), dtype=np.float64)
    out[rows_in, cols_in] = np.clip(solution, 0.0, 1.0)
    return out


def solve_ode(
    rhs: Callable[[float, NDArray[np.float64]], list[float]],
    y0: list[float],
    t_max: float,
    stops: list[Callable[[float, NDArray[np.float64]], float]],
    max_step: float,
) -> tuple[float, Callable[[FloatArray], NDArray[np.float64]]]:
    """Integrate dy/dt = rhs(t, y) from 0 (LSODA, which switches to a stiff method
    when needed) until t_max or until any stop function crosses zero. Returns the
    end time and a dense interpolant: times (n,) -> states (len(y0), n)."""
    for stop in stops:
        stop.terminal = True  # type: ignore[attr-defined]
    sol = solve_ivp(
        rhs,
        (0.0, t_max),
        y0,
        method="LSODA",
        rtol=1e-7,
        atol=1e-9,
        events=stops,
        dense_output=True,
        max_step=max_step,
    )
    dense = sol.sol

    def sample(times: FloatArray) -> NDArray[np.float64]:
        return np.asarray(dense(times), dtype=np.float64)

    return float(sol.t[-1]), sample


def minimize_lbfgs(
    fun: Callable[[NDArray[np.float64]], tuple[float, NDArray[np.float64]]],
    x0: NDArray[np.float64],
) -> NDArray[np.float64]:
    """The minimum of a smooth function that returns its own gradient."""
    from scipy.optimize import minimize

    return cast(NDArray[np.float64], minimize(fun, x0, jac=True, method="L-BFGS-B").x)
