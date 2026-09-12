"""Units a route needs: crossing units, junction units and repeaters, placed through the world."""

from typing import Any

from kohakulayout.ir import Refusal, Segment
from kohakulayout.ir.geometry import XY
from kohakulayout.physics.protocol import UnitPlacement
from kohakulayout.state.chain import recover
from kohakulayout.state.kernel import holder_kind
from kohakulayout.state.router.protocol import refuse

DISPLACEMENTS = 4


def emitter_at(world: Any, refusal: Refusal) -> str | None:
    """The field emitter unit the refusal names as the holder, or None."""
    holder = str(refusal.attrs.get("kl", {}).get("holder", ""))
    unit = (
        world.units.get(holder.removeprefix("unit:"))
        if holder.startswith("unit:")
        else None
    )
    if unit is None or not unit.owner.startswith("field:"):
        return None
    return unit.id


def place(world: Any, net_id: str, footprint: Any, xy: XY, what: str) -> str | Refusal:
    """Place a unit the route needs; a field emitter in its way is removed and the fields covered again."""
    unit_id = world.next_unit_id()
    spot = UnitPlacement(
        kind=footprint.id, footprint=footprint, x=xy[0], y=xy[1], owner=f"net:{net_id}"
    )
    refusal = world.place_unit(spot, unit_id)
    gone: list[Any] = []
    while refusal is not None and len(gone) < DISPLACEMENTS:
        emitter = emitter_at(world, refusal)
        if emitter is None:
            break
        gone.append(world.units[emitter])
        world.remove_unit(emitter)
        refusal = world.place_unit(spot, unit_id)
    if refusal is None and gone:
        refusal = recover(world, gone)
    if refusal is not None:
        return refuse(
            net_id, f"cannot place the {what} {footprint.id} at {xy}: {refusal.detail}"
        ).model_copy(update={"attrs": refusal.attrs})
    return unit_id


def unit_at(world: Any, layer: str, xy: XY, footprint_id: str) -> bool:
    """Whether a unit of this footprint still stands on the cell; a reused crossing may have gone with a ripped net."""
    for holder in world.kernel.holders_at(layer, xy):
        kind, ref = holder_kind(holder)
        if kind == "unit" and world.units[ref].footprint == footprint_id:
            return True
    return False


def crossings(
    world: Any, net: Any, plan_crossings: list[tuple[XY, str, bool]]
) -> list[str] | Refusal:
    out: list[str] = []
    layer = world.carrier_layer(net.carrier)
    for xy, other_id, reuse in plan_crossings:
        other = world.netlist.nets[other_id]
        rule = world.physics.carriers.crossing(net.carrier, other.carrier)
        if rule.mode != "unit" or rule.unit is None:
            continue
        if reuse and unit_at(world, layer, xy, rule.unit.id):
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


def has_unit(world: Any, layer: str, xy: XY) -> bool:
    """Whether any unit holds the cell on the layer."""
    return any(holder_kind(h)[0] == "unit" for h in world.kernel.holders_at(layer, xy))


def straight(cells: list[XY], index: int) -> bool:
    """Whether the cell lies on one line with its two neighbours on the path; an end never does."""
    if index <= 0 or index >= len(cells) - 1:
        return False
    before, after = cells[index - 1], cells[index + 1]
    return before[0] == after[0] or before[1] == after[1]


def repeaters(world: Any, net: Any, segments: list[Segment]) -> list[str] | Refusal:
    """A repeater on each stretch between units over the limit; a refusal without a repeater."""
    limit = world.physics.carriers.run_limit(net.carrier)
    footprint = world.physics.carriers.repeater(net.carrier)
    if limit is None:
        return []
    layer = world.carrier_layer(net.carrier)
    out: list[str] = []
    for segment in segments:
        cells = segment.cells
        start = 0
        while start < len(cells):
            end = next(
                (
                    i
                    for i in range(start, len(cells))
                    if has_unit(world, layer, cells[i])
                ),
                len(cells),
            )
            if end - start <= limit:
                start = end + 1
                continue
            if footprint is None:
                return refuse(
                    net.id,
                    f"a {net.carrier!r} run of {end - start} exceeds the limit of {limit} and no repeater exists",
                )
            index = next(
                (
                    i
                    for i in range(start + limit - 1, start + 1, -1)
                    if straight(cells, i)
                ),
                start + 1,
            )
            placed = place(world, net.id, footprint, cells[index], "repeater")
            if isinstance(placed, Refusal):
                return placed
            out.append(placed)
            start = index + 1
    return out


__all__ = [
    "crossings",
    "emitter_at",
    "has_unit",
    "junctions",
    "place",
    "recover",
    "repeaters",
    "straight",
    "unit_at",
]
