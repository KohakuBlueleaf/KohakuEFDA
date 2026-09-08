"""How reservations and regions price a cell for a carrier: corridor, wall, or the pack's answer."""

from typing import Any

from kohakulayout.ir.geometry import XY
from kohakulayout.state.router.protocol import Costs


def walls(world: Any, carrier: str) -> frozenset[XY]:
    """Cells a wire of ``carrier`` may never enter: regions the pack closes, and cells in no region."""
    regions = world.fabric.regions
    if not regions:
        return frozenset()
    closed: set[XY] = set()
    covered: set[XY] = set()
    for region_id, region in regions.items():
        cells = region.cells()
        covered |= cells
        if not world.physics.boundaries.crossing_region(carrier, region_id):
            closed |= cells
    width, height = world.fabric.width, world.fabric.height
    outside = {(x, y) for y in range(height) for x in range(width)} - covered
    return frozenset(closed | outside)


def reservation_price(world: Any, tag: str, carrier: str, costs: Costs) -> int | None:
    """The cost of entering a reserved cell: a corridor for its own carrier, a wall for any other."""
    reservation = world.reservations.get(tag)
    if reservation is None or reservation.carrier != carrier:
        return None
    return costs.corridor


__all__ = ["reservation_price", "walls"]
