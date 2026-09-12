"""How reservations and regions price a cell for a carrier, and where its units may not stand."""

from typing import Any

from kohakulayout.ir import Footprint
from kohakulayout.ir.geometry import XY
from kohakulayout.state.crossing import region_cells
from kohakulayout.state.router.protocol import Costs


def _closed(world: Any, allowed: Any) -> frozenset[XY]:
    regions = region_cells(world)
    if not regions:
        return frozenset()
    closed: set[XY] = set()
    covered: set[XY] = set()
    for region_id, cells in regions.items():
        covered |= cells
        if not allowed(region_id):
            closed |= cells
    width, height = world.fabric.width, world.fabric.height
    outside = {(x, y) for y in range(height) for x in range(width)} - covered
    return frozenset(closed | outside)


def walls(world: Any, carrier: str) -> frozenset[XY]:
    """Cells a wire of ``carrier`` may never enter: regions the pack closes, and cells in no region."""
    boundaries = world.physics.boundaries
    return _closed(world, lambda region: boundaries.crossing_region(carrier, region))


def unit_walls(world: Any, unit: Footprint | None) -> frozenset[XY]:
    """Cells the unit may never stand on: closed regions and cells in no region."""
    if unit is None:
        return frozenset()
    boundaries = world.physics.boundaries
    return _closed(world, lambda region: boundaries.unit_region(unit, region))


def reservation_price(world: Any, tag: str, carrier: str, costs: Costs) -> int | None:
    """The cost of entering a reserved cell: a corridor for its own carrier, a wall for any other."""
    reservation = world.reservations.get(tag)
    if reservation is None or reservation.carrier != carrier:
        return None
    return costs.corridor


__all__ = ["reservation_price", "unit_walls", "walls"]
