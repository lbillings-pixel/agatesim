"""A typed wrapper around ONNX Runtime, which ships no type information, so the
rest of the package stays under strict type checking."""
# pyright: basic

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray


class Session:
    """One model on the processor, with one input and its first output read."""

    def __init__(self, path: Path) -> None:
        import onnxruntime as ort

        self._session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self._input: str = self._session.get_inputs()[0].name

    def run(self, x: NDArray[np.float32]) -> NDArray[np.float32]:
        return np.asarray(self._session.run(None, {self._input: x})[0], np.float32)
