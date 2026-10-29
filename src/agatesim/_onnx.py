"""A typed wrapper around ONNX Runtime, which ships no type information, so the
rest of the package stays under strict type checking."""
# pyright: basic

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


class Session:
    """One model on the processor. `run` feeds its one input and reads its first
    output; `run_named` feeds inputs by name and reads every output. Without
    the memory arena, memory freed during a run goes back to the system (SAM's
    encoder peaks at 0.9 GB instead of 1.7 GB, about 0.1 s slower)."""

    def __init__(self, path: Path, *, arena: bool = True) -> None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.enable_cpu_mem_arena = arena
        self._session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        self._input: str = self._session.get_inputs()[0].name

    def run(self, x: NDArray[np.float32]) -> NDArray[np.float32]:
        return np.asarray(self._session.run(None, {self._input: x})[0], np.float32)

    def run_named(self, feeds: Mapping[str, NDArray[np.generic]]) -> list[NDArray[np.float32]]:
        return [np.asarray(y, np.float32) for y in self._session.run(None, dict(feeds))]
