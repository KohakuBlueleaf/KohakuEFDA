"""Units a route needs: crossing units, junction units and repeaters, placed through the world."""

from typing import Any

from kohakulayout.ir import Refusal, Segment
from kohakulayout.ir.geometry import XY
from kohakulayout.physics.protocol import UnitPlacement
from kohakulayout.state.router.protocol import refuse


def place(world: Any, net_id: str, footprint: Any, xy: XY, what: str) -> str | Refusal:
    unit_id = world.next_unit_id()
    spot = UnitPlacement(
        kind=footprint.id, footprint=footprint, x=xy[0], y=xy[1], owner=f"net:{net_id}"
    )
    refusal = world.place_unit(spot, unit_id)
    if refusal is not None:
        return refuse(
            net_id, f"cannot place the {what} {footprint.id} at {xy}: {refusal.detail}"
        )
    return unit_id


def crossings(
    world: Any, net: Any, plan_crossings: list[tuple[XY, str, bool]]
) -> list[str] | Refusal:
    out: list[str] = []
    for xy, other_id, reuse in plan_crossings:
        if reuse:
            continue
        other = world.netlist.nets[other_id]
        rule = world.physics.carriers.crossing(net.carrier, other.carrier)
        if rule.mode != "unit" or rule.unit is None:
            continue
        placed = place(world, net.id, rule.unit, xy, "crossing unit")
        if isinstance(placed, Refusal):
            return placed
        out.append(placed)
    return out


def junctions(
    world: Any, net: Any, plan_junctions: list[tuple[XY, str]]
) -> list[str] | Refusal:
    rule = world.physics.carriers.junction(net.carrier)
    if rule.mode != "unit":
        return []
    out: list[str] = []
    for xy, what in plan_junctions:
        footprint = rule.split if what == "split" else rule.merge
        if footprint is None:
            return refuse(
                net.id, f"a {what} at {xy} needs a unit the pack does not declare"
            )
        placed = place(world, net.id, footprint, xy, f"{what} unit")
        if isinstance(placed, Refusal):
            return placed
        out.append(placed)
    return out


def repeaters(world: Any, net: Any, segments: list[Segment]) -> list[str] | Refusal:
    limit = world.physics.carriers.run_limit(net.carrier)
    footprint = world.physics.carriers.repeater(net.carrier)
    if limit is None:
        return []
    if footprint is None:
        return refuse(
            net.id, f"{net.carrier!r} has a run limit of {limit} and no repeater"
        )
    out: list[str] = []
    for segment in segments:
        for index in range(limit, len(segment.cells) - 1, limit):
            placed = place(world, net.id, footprint, segment.cells[index], "repeater")
            if isinstance(placed, Refusal):
                return placed
            out.append(placed)
    return out


__all__ = ["crossings", "junctions", "place", "repeaters"]
