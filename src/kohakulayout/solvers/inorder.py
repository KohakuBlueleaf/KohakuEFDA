"""The in-order solver, the null solver: cells in flow order, each at the first anchor that takes it."""

from typing import Any

from kohakulayout.solvers.base import BaseSolver
from kohakulayout.solvers.protocol import Param
from kohakulayout.solvers.registry import register


@register
class InOrder(BaseSolver):
    id = "inorder"
    params = (
        Param(
            name="tries",
            type="int",
            default=64,
            doc="anchors attempted per cell before giving up on it",
        ),
    )

    def construct(self, ctx: Any) -> None:
        builder = ctx.builder()
        order, _ = builder.netlist.flow_order()
        for cell_id in order:
            if cell_id in builder.placements:
                continue
            self.place_one(ctx, cell_id, self.opts["tries"])
            ctx.frame("placed")

    def place_one(self, ctx: Any, cell_id: str, tries: int) -> bool:
        builder = ctx.builder()
        attempted = 0
        for anchor in builder.anchors(cell_id):
            if attempted >= tries:
                break
            if not builder.admits(cell_id, anchor.x, anchor.y, anchor.rot):
                continue
            attempted += 1
            result = ctx.attempt(
                lambda b, a=anchor: b.place(cell_id, a), label=f"place {cell_id}"
            )
            if result.ok:
                return True
        return False


__all__ = ["InOrder"]
