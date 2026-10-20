"""About how much memory an object holds: the bytes of the NumPy arrays and
search trees reachable from it, which is nearly all of a prepared 3D run.

Used to keep the server's caches within a memory budget rather than a count:
an H2 formation holds about half a gigabyte, a procedural one a few megabytes.
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Iterable
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

MAX_DEPTH = 12  # objects nested deeper than this aren't counted (none are, in practice)
TREE_OVERHEAD = 2.0  # a k-d tree's nodes and index, as a multiple of its points' bytes


def footprint(root: object) -> int:
    """Bytes of the arrays and k-d trees reachable from `root`, each counted
    once (views count their base array). Follows instance attributes, dataclass
    fields, containers and closures; not modules or classes."""
    seen: set[int] = set()
    total = 0
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        item: Any
        item, depth = stack.pop()
        obj: Any = item
        if depth > MAX_DEPTH or id(obj) in seen:
            continue
        seen.add(id(obj))
        if isinstance(obj, np.ndarray):
            owner = _owner(cast(NDArray[Any], obj))
            if owner is obj or id(owner) not in seen:
                seen.add(id(owner))
                total += int(owner.nbytes)
            continue
        if isinstance(obj, (str, bytes, int, float, bool, type, types.ModuleType)) or obj is None:
            continue
        data: object = getattr(obj, "data", None)
        if isinstance(data, np.ndarray) and hasattr(obj, "query"):  # a scipy k-d tree
            points = cast(NDArray[Any], data)
            total += int(points.nbytes * (1 + TREE_OVERHEAD))
            seen.add(id(points))
            continue
        children: list[Any] = []
        if isinstance(obj, (list, tuple, set, frozenset)):
            children.extend(cast(Iterable[Any], obj))
        elif isinstance(obj, dict):
            children.extend(cast(dict[Any, Any], obj).values())
        elif isinstance(obj, types.FunctionType):
            children.extend(c.cell_contents for c in obj.__closure__ or () if _filled(c))
        else:
            if dataclasses.is_dataclass(obj):
                children.extend(getattr(obj, f.name, None) for f in dataclasses.fields(obj))
            attributes: dict[str, Any] = getattr(obj, "__dict__", {})
            children.extend(attributes.values())
        stack.extend((c, depth + 1) for c in children)
    return total


def _owner(array: NDArray[Any]) -> NDArray[Any]:
    """The array that owns a view's memory (the array itself if it owns it)."""
    base: object = array.base
    return _owner(base) if isinstance(base, np.ndarray) else array


def _filled(cell: types.CellType) -> bool:
    try:
        cell.cell_contents  # noqa: B018
    except ValueError:  # an empty cell
        return False
    return True
