"""The recording kernel: every call logged as one JSON line around any kernel, and a replay into another."""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from kohakulayout.ir.geometry import XY
from kohakulayout.state.kernel.protocol import Holder

MUTATIONS = ("occupy", "free", "clear", "load")


class RecordingKernel:
    """Forwards to ``inner``; mutations are appended to ``log`` as ``{"op", "args"}`` lines."""

    def __init__(self, inner: Any, log: list[str] | None = None) -> None:
        self.inner = inner
        self.log: list[str] = log if log is not None else []

    @property
    def width(self) -> int:
        return self.inner.width

    @property
    def height(self) -> int:
        return self.inner.height

    @property
    def layers(self) -> tuple[str, ...]:
        return self.inner.layers

    def _record(self, op: str, *args: Any) -> None:
        self.log.append(
            json.dumps({"op": op, "args": list(args)}, separators=(",", ":"))
        )

    def occupy(self, layer: str, cells: Iterable[XY], holder: Holder) -> None:
        cells = [list(c) for c in cells]
        self._record("occupy", layer, cells, holder)
        self.inner.occupy(layer, [tuple(c) for c in cells], holder)

    def free(self, layer: str, cells: Iterable[XY], holder: Holder) -> None:
        cells = [list(c) for c in cells]
        self._record("free", layer, cells, holder)
        self.inner.free(layer, [tuple(c) for c in cells], holder)

    def clear(self) -> None:
        self._record("clear")
        self.inner.clear()

    def load(self, blob: bytes) -> None:
        self._record("load", blob.decode("utf-8"))
        self.inner.load(blob)

    def holders_at(self, layer: str, xy: XY) -> tuple[Holder, ...]:
        return self.inner.holders_at(layer, xy)

    def holders(
        self, layer: str, cells: Iterable[XY]
    ) -> tuple[tuple[Holder, ...], ...]:
        return self.inner.holders(layer, cells)

    def free_for(self, layer: str, cells: Iterable[XY]) -> bool:
        return self.inner.free_for(layer, cells)

    def cells_of(self, holder: Holder) -> dict[str, frozenset[XY]]:
        return self.inner.cells_of(holder)

    def holders_on(self, layer: str) -> tuple[Holder, ...]:
        return self.inner.holders_on(layer)

    def holders_map(self, layer: str) -> Mapping[XY, tuple[Holder, ...]]:
        return self.inner.holders_map(layer)

    def extent(
        self, layer: str | None = None, mask: frozenset[XY] | None = None
    ) -> tuple[int, int, int, int] | None:
        return self.inner.extent(layer, mask)

    def occupancy(self, layer: str) -> np.ndarray:
        return self.inner.occupancy(layer)

    def integral(self, layer: str) -> np.ndarray:
        return self.inner.integral(layer)

    def save(self) -> bytes:
        return self.inner.save()

    def dump(self, path: Path) -> Path:
        path.write_text("\n".join(self.log) + ("\n" if self.log else ""))
        return path


def replay(log: Iterable[str], kernel: Any) -> Any:
    """Drive ``kernel`` with a recorded log; the kernel after the last line is returned."""
    for line in log:
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        op, args = entry["op"], entry["args"]
        if op == "occupy":
            kernel.occupy(args[0], [tuple(c) for c in args[1]], args[2])
        elif op == "free":
            kernel.free(args[0], [tuple(c) for c in args[1]], args[2])
        elif op == "clear":
            kernel.clear()
        elif op == "load":
            kernel.load(args[0].encode("utf-8"))
    return kernel


__all__ = ["MUTATIONS", "RecordingKernel", "replay"]
