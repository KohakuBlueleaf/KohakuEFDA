"""The gates verify deck: edge cells on their edge, fan-out within the limit."""

from collections.abc import Iterable
from typing import Any

from kohakulayout.ir import Finding, Layout
from kohakulayout.physics import FunctionRule
from kohakulayout.templates.physics.gates.boundaries import edge_side, touches
from kohakulayout.templates.physics.gates.library import FANOUT_LIMIT


def edge(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    for cell_id, placement in layout.placements.items():
        cell = world.netlist.cells.get(cell_id)
        side = edge_side(cell) if cell is not None else None
        if side is not None and not touches(world, placement, side):
            yield Finding(
                rule="gates.edge",
                severity="error",
                subject=f"cell:{cell_id}",
                message=f"{cell_id} must sit on the {side} edge",
            )


def fanout(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    for net in world.netlist.nets.values():
        if len(net.sinks) > FANOUT_LIMIT:
            yield Finding(
                rule="gates.fanout",
                severity="error",
                subject=f"net:{net.id}",
                message=f"{net.id} drives {len(net.sinks)} sinks; the limit is {FANOUT_LIMIT}",
                attrs={"gates": {"limit": FANOUT_LIMIT, "sinks": len(net.sinks)}},
            )


RULES = (
    FunctionRule("gates.edge", "error", edge),
    FunctionRule("gates.fanout", "error", fanout),
)

__all__ = ["RULES", "edge", "fanout"]
