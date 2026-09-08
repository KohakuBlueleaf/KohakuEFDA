"""The pure Python kernel: dictionaries per layer, the reference the native twin must match."""

import json
from collections.abc import Iterable, Mapping
from types import MappingProxyType

import numpy as np

from kohakulayout.ir.geometry import XY
from kohakulayout.state.kernel.protocol import Holder


class PyKernel:
    def __init__(self, width: int, height: int, layers: tuple[str, ...]) -> None:
        self.width = width
        self.height = height
        self.layers = tuple(layers)
        self._grid: dict[str, dict[XY, tuple[Holder, ...]]] = {
            layer: {} for layer in self.layers
        }
        self._index: dict[Holder, dict[str, set[XY]]] = {}

    # ------------------------------------------------------------ mutation
    def occupy(self, layer: str, cells: Iterable[XY], holder: Holder) -> None:
        grid = self._grid[layer]
        mine = self._index.setdefault(holder, {}).setdefault(layer, set())
        for xy in cells:
            held = grid.get(xy, ())
            if holder not in held:
                grid[xy] = tuple(sorted((*held, holder)))
            mine.add(xy)

    def free(self, layer: str, cells: Iterable[XY], holder: Holder) -> None:
        grid = self._grid[layer]
        mine = self._index.get(holder, {}).get(layer)
        for xy in cells:
            held = grid.get(xy)
            if held is None:
                continue
            rest = tuple(h for h in held if h != holder)
            if rest:
                grid[xy] = rest
            else:
                del grid[xy]
            if mine is not None:
                mine.discard(xy)
        if mine is not None and not mine:
            del self._index[holder][layer]
            if not self._index[holder]:
                del self._index[holder]

    def clear(self) -> None:
        for layer in self.layers:
            self._grid[layer].clear()
        self._index.clear()

    # ------------------------------------------------------------- queries
    def holders_at(self, layer: str, xy: XY) -> tuple[Holder, ...]:
        return self._grid[layer].get(xy, ())

    def holders(
        self, layer: str, cells: Iterable[XY]
    ) -> tuple[tuple[Holder, ...], ...]:
        grid = self._grid[layer]
        return tuple(grid.get(xy, ()) for xy in cells)

    def free_for(self, layer: str, cells: Iterable[XY]) -> bool:
        grid = self._grid[layer]
        return all(xy not in grid for xy in cells)

    def cells_of(self, holder: Holder) -> dict[str, frozenset[XY]]:
        return {
            layer: frozenset(cells)
            for layer, cells in self._index.get(holder, {}).items()
        }

    def holders_map(self, layer: str) -> Mapping[XY, tuple[Holder, ...]]:
        """The layer's occupied cells and their holders; a read-only view, valid until the next mutation."""
        return MappingProxyType(self._grid[layer])

    def holders_on(self, layer: str) -> tuple[Holder, ...]:
        return tuple(
            sorted(h for h, layers in self._index.items() if layers.get(layer))
        )

    def extent(
        self, layer: str | None = None, mask: frozenset[XY] | None = None
    ) -> tuple[int, int, int, int] | None:
        layers = self.layers if layer is None else (layer,)
        xs: list[int] = []
        ys: list[int] = []
        for name in layers:
            for x, y in self._grid[name]:
                if mask is None or (x, y) in mask:
                    xs.append(x)
                    ys.append(y)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)

    def occupancy(self, layer: str) -> np.ndarray:
        out = np.zeros((self.height, self.width), dtype=np.int32)
        for x, y in self._grid[layer]:
            if 0 <= x < self.width and 0 <= y < self.height:
                out[y, x] = 1
        return out

    def integral(self, layer: str) -> np.ndarray:
        """The summed-area table of the occupancy, ``(height + 1) x (width + 1)``."""
        table = np.zeros((self.height + 1, self.width + 1), dtype=np.int64)
        table[1:, 1:] = self.occupancy(layer).cumsum(axis=0).cumsum(axis=1)
        return table

    # ---------------------------------------------------------- persistence
    def save(self) -> bytes:
        payload = {
            "width": self.width,
            "height": self.height,
            "layers": {
                layer: [
                    [x, y, list(held)]
                    for (x, y), held in sorted(self._grid[layer].items())
                ]
                for layer in self.layers
            },
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )

    def load(self, blob: bytes) -> None:
        payload = json.loads(blob.decode("utf-8"))
        self.clear()
        for layer, cells in payload["layers"].items():
            for x, y, held in cells:
                for holder in held:
                    self.occupy(layer, [(x, y)], holder)
