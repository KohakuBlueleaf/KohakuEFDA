"""Zone membership: which Gas Dispersing Unit each environment machine belongs to.

A zone is the 13×13 square around a 3×3 unit (game-knowledge ENV-01) and must contain the
whole footprint of every machine it serves (ENV-02). A machine can lie inside when it is at
most the unit's reach (5) long in the dimension that stands beside the unit, and a group fits
when its footprints and the unit stay within half of the zone (the planner's ``ZONE_FILL``).
Members are assigned first-fit by decreasing footprint; the plan's zone count is a lower bound
and a machine no planned zone can hold opens another.
"""

import logging

from kohakuefda.model.cells import CellInstance
from kohakuefda.model.sinks import ZONE_SIDE
from kohakuefda.plan.lp import ZONE_FILL

log = logging.getLogger(__name__)
UNIT_SIZE = 3
REACH = 5
ZONE_CELLS = int(ZONE_SIDE * ZONE_SIDE * ZONE_FILL)


def member_fits(cell: CellInstance) -> bool:
    return (cell.width <= REACH and cell.height <= ZONE_SIDE) or (
        cell.height <= REACH and cell.width <= ZONE_SIDE
    )


def group_fits(members: list[CellInstance]) -> bool:
    footprint = sum(c.area for c in members) + UNIT_SIZE * UNIT_SIZE
    return footprint <= ZONE_CELLS and all(member_fits(c) for c in members)


def assign_zones(members: list[CellInstance], planned: int) -> list[list[CellInstance]]:
    """Groups of members that each fit one zone; at least ``planned`` groups when members
    allow, more when they do not fit."""
    groups: list[list[CellInstance]] = [[] for _ in range(max(planned, 1))]
    for cell in sorted(members, key=lambda c: -c.area):
        placed = False
        for group in groups:
            if group_fits([*group, cell]):
                group.append(cell)
                placed = True
                break
        if not placed:
            groups.append([cell])
    result = [g for g in groups if g] or groups[:1]
    log.debug("assigned %d member(s) to %d zone group(s)", len(members), len(result))
    return result
