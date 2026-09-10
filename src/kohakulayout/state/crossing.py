"""Where a wire may cross another on one cell: the other runs straight through, the pack allows it, and a crossing unit can stand there.

The placement chain asks it for an attach cell another net's wire holds; the path finder
asks it for every cell a path enters and for the cells a path starts or ends on.
"""

from typing import Any

from kohakulayout.ir import Footprint
from kohakulayout.ir.geometry import XY, footprint_cells
from kohakulayout.state.kernel import holder_kind

AXES: tuple[XY, XY] = ((1, 0), (0, 1))


def straight_through(
    world: Any,
    layer: str,
    other_net: str,
    xy: XY,
    direction: XY,
    port: XY | None = None,
    bent: bool = False,
) -> bool:
    """Whether the other net's wire runs through ``xy`` perpendicular to ``direction``; its port behind an attach cell counts as the wire's own side; with ``bent`` one side across is enough, the wire may turn on the cell."""
    if other_net not in world.wires:
        return False
    holder = f"wire:{other_net}"
    kernel = world.kernel

    def side(cell: XY) -> bool:
        return cell == port or holder in kernel.holders_at(layer, cell)

    px, py = direction[1], direction[0]
    x, y = xy
    if bent:
        return side((x + px, y + py)) or side((x - px, y - py))
    across = side((x + px, y + py)) and side((x - px, y - py))
    along = side((x + direction[0], y + direction[1])) or side(
        (x - direction[0], y - direction[1])
    )
    return across and not along


def occluded_free(
    world: Any, unit: Footprint, xy: XY, ignore: frozenset[str] = frozenset()
) -> bool:
    """Whether the layers a unit at ``xy`` occludes are free there, the holders in ``ignore`` (units a path displaces) not counted; its own layer holds the wires it crosses."""
    cells = footprint_cells(xy[0], xy[1], unit.width, unit.height, 0)
    if not all(world.in_grid(c) for c in cells):
        return False
    if not ignore:
        return all(world.kernel.free_for(layer, cells) for layer in unit.occludes)
    return all(
        h in ignore
        for layer in unit.occludes
        for c in cells
        for h in world.kernel.holders_at(layer, c)
    )


def only_wires(holders: tuple[str, ...]) -> bool:
    return all(holder_kind(h)[0] == "wire" for h in holders)


def crossable(world: Any, layer: str, carrier: str, other_net: str, xy: XY) -> bool:
    """Whether a wire of ``carrier`` may cross the other net's wire on this cell along either axis: the rule allows it, the other wire runs straight through, and a crossing unit, when one is needed, has the cell to itself."""
    other = world.netlist.nets.get(other_net)
    if other is None:
        return False
    rule = world.physics.carriers.crossing(carrier, other.carrier)
    if rule.mode == "forbidden":
        return False
    if not any(
        straight_through(world, layer, other_net, xy, axis, None, rule.bent)
        for axis in AXES
    ):
        return False
    if rule.mode != "unit":
        return True
    return (
        rule.unit is not None
        and only_wires(world.kernel.holders_at(layer, xy))
        and occluded_free(world, rule.unit, xy)
    )


__all__ = ["AXES", "crossable", "occluded_free", "only_wires", "straight_through"]
