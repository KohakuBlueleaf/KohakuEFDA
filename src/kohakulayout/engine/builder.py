"""The builder: the only door from a solver to the world. Every mutation is charged and journaled."""

from collections.abc import Iterable
from typing import Any

from kohakulayout.ir import Layout, Refusal
from kohakulayout.ir.geometry import XY
from kohakulayout.physics.protocol import Anchor


class Builder:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.world = ctx.world
        self.last: Refusal | None = None

    # ---------------------------------------------------------- mutations
    def _note(self, refusal: Refusal | None) -> Refusal | None:
        self.last = refusal
        if refusal is not None:
            self.ctx.refused(refusal)
        return refusal

    def place(
        self, cell: str, anchor: Anchor | tuple[int, int] | tuple[int, int, int]
    ) -> Refusal | None:
        if isinstance(anchor, Anchor):
            x, y, rot = anchor.x, anchor.y, anchor.rot
        else:
            x, y = anchor[0], anchor[1]
            rot = anchor[2] if len(anchor) > 2 else 0
        refusal = self.world.place(cell, x, y, rot)
        self.ctx.charge(1)
        return self._note(refusal)

    def place_instance(
        self, instance: str, x: int, y: int, rot: int = 0
    ) -> Refusal | None:
        refusal = self.world.place_instance(instance, x, y, rot)
        self.ctx.charge(1)
        return self._note(refusal)

    def withdraw(self, cell: str) -> None:
        self.world.withdraw(cell)
        self.ctx.charge(1)

    def route(self, net: str) -> Refusal | None:
        refusal = self.world.route(net)
        self.ctx.charge(1)
        return self._note(refusal)

    def unroute(self, net: str) -> None:
        self.world.unroute(net)

    def reserve(
        self, tag: str, layer: str, cells: Iterable[XY], carrier: str | None = None
    ) -> None:
        self.world.reserve(tag, layer, cells, carrier)

    def release(self, tag: str) -> None:
        self.world.release(tag)

    # ---------------------------------------------------------- atomicity
    def mark(self) -> int:
        return self.world.mark()

    def restore(self, mark: int) -> None:
        self.world.rollback_to(mark)

    def transaction(self) -> Any:
        return self.world.transaction()

    # ------------------------------------------------------------ queries
    def anchors(self, cell: str) -> Iterable[Anchor]:
        return self.world.anchors(cell)

    def admits(self, cell: str, x: int, y: int, rot: int = 0) -> bool:
        return self.world.admits(cell, x, y, rot)

    def first_open(
        self, cell: str, anchors: Iterable[Anchor] | None = None
    ) -> Anchor | None:
        return self.world.first_open(cell, anchors)

    def diagnostic(self) -> Refusal | None:
        return self.last

    @property
    def placements(self) -> dict[str, Any]:
        return self.world.placements

    @property
    def netlist(self) -> Any:
        return self.world.netlist

    def unplaced(self) -> tuple[str, ...]:
        return tuple(
            c for c in self.world.netlist.cells if c not in self.world.placements
        )

    def unrouted(self) -> tuple[str, ...]:
        return tuple(n.id for n in self.world.unrouted())

    def extent(self) -> tuple[int, int, int, int]:
        return self.world.extent()

    def finish(self) -> Layout:
        return self.world.freeze()


__all__ = ["Builder"]
