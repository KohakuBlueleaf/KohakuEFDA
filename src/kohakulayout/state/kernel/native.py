"""The native kernel: the Rust grid behind the same protocol as the Python one, byte for byte."""

from collections.abc import Iterable, Mapping

import numpy as np

from kohakulayout._rust import HAS_RUST, kohakulayout_rs
from kohakulayout.errors import NotAvailable
from kohakulayout.ir.geometry import XY
from kohakulayout.state.kernel.protocol import Holder


class NativeKernel:
    def __init__(self, width: int, height: int, layers: tuple[str, ...]) -> None:
        if not HAS_RUST:
            raise NotAvailable(
                "kohakulayout_rs is not built; run maturin develop in src/kohakulayout-rs or use kernel='python'"
            )
        self.width = width
        self.height = height
        self.layers = tuple(layers)
        self._grid = kohakulayout_rs.Grid(width, height, list(layers))

    def occupy(self, layer: str, cells: Iterable[XY], holder: Holder) -> None:
        self._grid.occupy(layer, [tuple(c) for c in cells], holder)

    def free(self, layer: str, cells: Iterable[XY], holder: Holder) -> None:
        self._grid.free(layer, [tuple(c) for c in cells], holder)

    def set_runs(
        self, layer: str, holder: Holder, runs: Iterable[tuple[XY, int]]
    ) -> None:
        self._grid.set_runs(layer, holder, [(xy[0], xy[1], mask) for xy, mask in runs])

    def run_at(self, layer: str, holder: Holder, xy: XY) -> int:
        return self._grid.run_at(layer, holder, tuple(xy))

    def note_unit(self, unit_id: str, footprint: str, owner: str, field: bool) -> None:
        self._grid.note_unit(unit_id, footprint, owner, field)

    def clear(self) -> None:
        self._grid.clear()

    def holders_at(self, layer: str, xy: XY) -> tuple[Holder, ...]:
        return tuple(self._grid.holders_at(layer, tuple(xy)))

    def holders(
        self, layer: str, cells: Iterable[XY]
    ) -> tuple[tuple[Holder, ...], ...]:
        return tuple(
            tuple(h) for h in self._grid.holders(layer, [tuple(c) for c in cells])
        )

    def free_for(self, layer: str, cells: Iterable[XY]) -> bool:
        return self._grid.free_for(layer, [tuple(c) for c in cells])

    def cells_of(self, holder: Holder) -> dict[str, frozenset[XY]]:
        return {
            layer: frozenset(tuple(c) for c in cells)
            for layer, cells in self._grid.cells_of(holder).items()
        }

    def holders_on(self, layer: str) -> tuple[Holder, ...]:
        return tuple(self._grid.holders_on(layer))

    def holders_map(self, layer: str) -> Mapping[XY, tuple[Holder, ...]]:
        return {tuple(xy): tuple(held) for xy, held in self._grid.holders_map(layer)}

    def extent(
        self, layer: str | None = None, mask: frozenset[XY] | None = None
    ) -> tuple[int, int, int, int] | None:
        found = self._grid.extent(
            layer, [tuple(c) for c in mask] if mask is not None else None
        )
        return tuple(found) if found is not None else None

    def occupancy(self, layer: str) -> np.ndarray:
        flat = np.frombuffer(bytes(self._grid.occupancy(layer)), dtype=np.uint8)
        return flat.reshape((self.height, self.width)).astype(np.int8)

    def integral(self, layer: str) -> np.ndarray:
        table = np.zeros((self.height + 1, self.width + 1), dtype=np.int64)
        table[1:, 1:] = self.occupancy(layer).cumsum(axis=0).cumsum(axis=1)
        return table

    def save(self) -> bytes:
        return bytes(self._grid.save())

    def load(self, blob: bytes) -> None:
        self._grid.load(list(blob))


__all__ = ["NativeKernel"]
