"""Units a route needs: crossing units, junction units and repeaters, placed through the world."""

from typing import Any

from kohakulayout.ir import Refusal, Segment
from kohakulayout.ir.geometry import XY, footprint_cells
from kohakulayout.physics.protocol import UnitPlacement
from kohakulayout.state.chain import cover
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


def recover(world: Any) -> Refusal | None:
    """Cover again every placed cell a displaced emitter left short of a need."""
    fields = world.physics.fields
    emitters = {e.kind: e for e in fields.emitters()}
    for cell_id, placement in list(world.placements.items()):
        cell = world.netlist.cells[cell_id]
        needs = [k for k in fields.needs(cell) if k in emitters]
        if not needs:
            continue
        fp = world.footprint_of(cell_id)
        cells = footprint_cells(
            placement.x, placement.y, fp.width, fp.height, placement.rot
        )
        short = False
        for kind in needs:
            covered = world.field_coverage(kind)
            hit = (
                any(c in covered for c in cells)
                if emitters[kind].reach.partial
                else all(c in covered for c in cells)
            )
            short = short or not hit
        if short:
            refusal = cover(world, cell, cells)
            if refusal is not None:
                return refusal
    return None


def place(world: Any, net_id: str, footprint: Any, xy: XY, what: str) -> str | Refusal:
    """Place a unit the route needs; a field emitter in its way is removed and the fields covered again."""
    unit_id = world.next_unit_id()
    spot = UnitPlacement(
        kind=footprint.id, footprint=footprint, x=xy[0], y=xy[1], owner=f"net:{net_id}"
    )
    refusal = world.place_unit(spot, unit_id)
    displaced = 0
    while refusal is not None and displaced < DISPLACEMENTS:
        emitter = emitter_at(world, refusal)
        if emitter is None:
            break
        world.remove_unit(emitter)
        displaced += 1
        refusal = world.place_unit(spot, unit_id)
    if refusal is None and displaced:
        refusal = recover(world)
    if refusal is not None:
        return refuse(
            net_id, f"cannot place the {what} {footprint.id} at {xy}: {refusal.detail}"
        ).model_copy(update={"attrs": refusal.attrs})
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
        longest = max((len(s.cells) for s in segments), default=0)
        if longest > limit:
            return refuse(
                net.id,
                f"a {net.carrier!r} run of {longest} exceeds the limit of {limit} and no repeater exists",
            )
        return []
    out: list[str] = []
    for segment in segments:
        cells = segment.cells
        start = 0
        while len(cells) - start > limit:
            index = min(start + limit, len(cells) - 2)
            if index <= start:
                return refuse(
                    net.id,
                    f"a {net.carrier!r} run of {len(cells) - start} exceeds the limit of {limit} with no cell for a repeater",
                )
            placed = place(world, net.id, footprint, cells[index], "repeater")
            if isinstance(placed, Refusal):
                return placed
            out.append(placed)
            start = index + 1
    return out


__all__ = ["crossings", "emitter_at", "junctions", "place", "recover", "repeaters"]
