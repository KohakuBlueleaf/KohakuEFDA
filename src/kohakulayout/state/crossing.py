"""Where a wire may cross another on one cell: the other runs straight through, the pack allows it, and a crossing unit can stand there.

A wire's run on a cell is the set of sides it continues to there, kept by the kernel as
bits ``N=1 E=2 S=4 W=8`` and written by the world from the wire's segments and the port
behind each attach cell it uses. The placement chain asks for an attach cell another
net's wire holds; the path finder asks for every cell a path enters and for the cells a
path starts or ends on.
"""

from typing import Any

from kohakulayout.ir import Footprint
from kohakulayout.ir.geometry import XY, footprint_cells
from kohakulayout.state.kernel import holder_kind

AXES: tuple[XY, XY] = ((1, 0), (0, 1))
SIDES: dict[XY, int] = {(0, -1): 1, (1, 0): 2, (0, 1): 4, (-1, 0): 8}


def side_bit(a: XY, b: XY) -> int:
    """The run bit of the side ``b`` lies on from ``a``; zero when they are not neighbours."""
    return SIDES.get((b[0] - a[0], b[1] - a[1]), 0)


def straight_through(
    world: Any,
    layer: str,
    other_net: str,
    xy: XY,
    direction: XY,
    bent: bool = False,
) -> bool:
    """Whether the other net's wire crosses a move along ``direction`` straight at ``xy``."""
    run = world.kernel.run_at(layer, f"wire:{other_net}", xy)
    if not run:
        return False
    px, py = direction[1], direction[0]

    def side(dx: int, dy: int) -> bool:
        return bool(run & SIDES.get((dx, dy), 0))

    if bent:
        return side(px, py) or side(-px, -py)
    across = side(px, py) and side(-px, -py)
    along = side(direction[0], direction[1]) or side(-direction[0], -direction[1])
    return across and not along


_REGIONS: dict[int, tuple[Any, dict[str, frozenset[XY]]]] = {}


def region_cells(world: Any) -> dict[str, frozenset[XY]]:
    """Every region's cells, built once per fabric."""
    fabric = world.fabric
    hit = _REGIONS.get(id(fabric))
    if hit is None or hit[0] is not fabric:
        hit = (fabric, {rid: frozenset(r.cells()) for rid, r in fabric.regions.items()})
        _REGIONS[id(fabric)] = hit
    return hit[1]


def unit_allowed(world: Any, unit: Footprint, xy: XY) -> bool:
    """Whether the pack lets the unit stand in every region holding ``xy``."""
    regions = region_cells(world)
    if not regions:
        return True
    boundaries = world.physics.boundaries
    hits = [rid for rid, cells in regions.items() if xy in cells]
    return bool(hits) and all(boundaries.unit_region(unit, rid) for rid in hits)


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
        straight_through(world, layer, other_net, xy, axis, rule.bent) for axis in AXES
    ):
        return False
    if rule.mode != "unit":
        return True
    return (
        rule.unit is not None
        and only_wires(world.kernel.holders_at(layer, xy))
        and unit_allowed(world, rule.unit, xy)
        and occluded_free(world, rule.unit, xy)
    )


__all__ = [
    "AXES",
    "SIDES",
    "crossable",
    "occluded_free",
    "only_wires",
    "region_cells",
    "side_bit",
    "straight_through",
    "unit_allowed",
]
