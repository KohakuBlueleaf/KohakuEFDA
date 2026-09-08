"""The copyable minimal solver: everything a strategy owes the engine, and nothing about search.

Copy this file, rename the class and its id, and fill ``construct`` and ``improve``.
"""

from typing import Any

from kohakulayout.solvers import BaseSolver, Param, register


@register
class Skeleton(BaseSolver):
    id = "skeleton"
    params = (
        Param(
            name="rounds",
            type="int",
            default=1,
            doc="improvement passes over the placed cells",
        ),
    )

    def construct(self, ctx: Any) -> None:
        """Place every cell, in flow order, at the first anchor the world admits."""
        builder = ctx.builder()
        order, _ = builder.netlist.flow_order()
        for cell_id in order:
            if cell_id in builder.placements:
                continue
            for anchor in builder.anchors(cell_id):
                if not builder.admits(cell_id, anchor.x, anchor.y, anchor.rot):
                    continue
                if ctx.attempt(
                    lambda b, a=anchor, c=cell_id: b.place(c, a),
                    label=f"place {cell_id}",
                ).ok:
                    break
            ctx.frame("placed")

    def improve(self, ctx: Any) -> None:
        """One idea of an improvement loop: try each cell one step left, keep it when the assessment ranks better."""
        builder = ctx.builder()
        for _ in range(self.opts["rounds"]):
            for cell_id in list(builder.placements):
                placement = builder.placements[cell_id]
                token = ctx.snapshot()
                result = ctx.attempt(
                    lambda b, c=cell_id, p=placement: _shift_left(b, c, p),
                    label=f"shift {cell_id}",
                )
                if not result.ok or ctx.consider(token) is None:
                    ctx.restore(token)
            ctx.frame("improved")


def _shift_left(builder: Any, cell_id: str, placement: Any) -> Any:
    builder.withdraw(cell_id)
    return builder.place(cell_id, (placement.x - 1, placement.y, placement.rot))


__all__ = ["Skeleton"]
