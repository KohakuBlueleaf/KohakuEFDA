"""The placement failure chain: what a placement must pass before the world holds it.

Every check names its stage from the chain (legal, region, overlap, port_shut, field);
the physics orders them through ``diagnose``.
"""

from collections.abc import Iterable
from typing import Any

from kohakulayout.ir import Footprint, Refusal
from kohakulayout.ir.geometry import XY, footprint_cells
from kohakulayout.physics.fields import reach_cells
from kohakulayout.physics.protocol import Occupant
from kohakulayout.state.attach import options_at
from kohakulayout.state.crossing import crossable
from kohakulayout.state.kernel import holder_kind


def refusal(stage: str, cell_id: str, detail: str) -> Refusal:
    return Refusal(stage=stage, subject=f"cell:{cell_id}", detail=detail)


def inspect(
    world: Any,
    cell: Any,
    fp: Footprint,
    x: int,
    y: int,
    rot: int,
    cells: tuple[XY, ...],
    layers: tuple[str, ...],
) -> tuple[list[Refusal], list[str], list[str]]:
    """Every failure before occupancy, the nets the placement rips (wires and route units under it), and the field emitters it displaces."""
    failures: list[Refusal] = []
    if rot not in fp.rotations:
        failures.append(refusal("legal", cell.id, f"rotation r{rot} is not allowed"))
    if not all(world.in_grid(c) for c in cells):
        failures.append(refusal("region", cell.id, "leaves the grid"))
    elif not all(world.in_build(c) for c in cells):
        failures.append(refusal("region", cell.id, "outside the build region"))
    occupant = Occupant(kind="cell", id=cell.id)
    ripped: list[str] = []
    displaced: list[str] = []
    for layer in layers:
        for xy in cells:
            blocker = world.may_occupy(layer, xy, occupant)
            if blocker is None:
                continue
            kind, ref = holder_kind(blocker)
            owner = displaceable(world, kind, ref)
            if owner is not None:
                target = ripped if owner.startswith("net:") else displaced
                owner_id = owner.split(":", 1)[1]
                if owner_id not in target:
                    target.append(owner_id)
                continue
            failures.append(
                refusal("overlap", cell.id, f"{blocker} holds {xy} on {layer}")
            )
            break
    failures += port_shut(world, cell, fp, x, y, rot, cells, layers)
    return failures, ripped, [u for u in displaced if u in world.units]


def displaceable(world: Any, kind: str, ref: str) -> str | None:
    """What a footprint may push out of a cell: ``net:<id>`` for a wire or a route unit (ripped and re-routed, with a router), ``unit:<id>`` for a field emitter (placed again); None for anything else."""
    if kind == "wire":
        return f"net:{ref}" if world.router is not None else None
    if kind == "unit":
        unit = world.units.get(ref)
        if unit is None:
            return None
        if unit.owner.startswith("field:"):
            return f"unit:{ref}"
        if unit.owner.startswith("net:") and world.router is not None:
            return unit.owner
    return None


def recover(world: Any, gone: Iterable[Any] = ()) -> Refusal | None:
    """Cover again every placed cell a displaced emitter left short of a need; with ``gone`` (the emitters removed) only the cells they reached are looked at."""
    fields = world.physics.fields
    emitters = {e.kind: e for e in fields.emitters()}
    by_footprint = {e.footprint.id: e for e in emitters.values()}
    lost: set[XY] | None = None
    for unit in gone:
        emitter = by_footprint.get(unit.footprint)
        if emitter is not None:
            lost = (lost or set()) | reach_cells(emitter, unit.x, unit.y)
    if gone and not lost:
        return None
    covered: dict[str, frozenset[XY]] = {}
    for cell_id, placement in list(world.placements.items()):
        cell = world.netlist.cells[cell_id]
        needs = [k for k in fields.needs(cell) if k in emitters]
        if not needs:
            continue
        fp = world.footprint_of(cell_id)
        cells = footprint_cells(
            placement.x, placement.y, fp.width, fp.height, placement.rot
        )
        if lost is not None and lost.isdisjoint(cells):
            continue
        short = False
        for kind in needs:
            if kind not in covered:
                covered[kind] = world.field_coverage(kind)
            hit = (
                any(c in covered[kind] for c in cells)
                if emitters[kind].reach.partial
                else all(c in covered[kind] for c in cells)
            )
            short = short or not hit
        if short:
            refusal = cover(world, cell, cells)
            if refusal is not None:
                return refusal
            covered.clear()
    return None


def port_shut(
    world: Any,
    cell: Any,
    fp: Footprint,
    x: int,
    y: int,
    rot: int,
    cells: tuple[XY, ...],
    layers: tuple[str, ...],
    owners: dict[str, dict[XY, str]] | None = None,
) -> list[Refusal]:
    """Every pin of the cell keeps a port whose attach cell is open, and the cell leaves every other placed pin one."""
    failures: list[Refusal] = []
    owners = world.open_attach_owners() if owners is None else owners
    for pin in world.netlist.pins_of(cell.id):
        options = options_at(fp, pin, x, y, rot)
        if not options:
            continue
        layer = world.carrier_layer(pin.carrier)
        faults = [
            _shut_by(world, layer, attach, owners, cell.id, pin)
            for _, attach, _ in options
        ]
        if all(fault is not None for fault in faults):
            failures.append(refusal("port_shut", cell.id, f"pin {pin.id} {faults[0]}"))
    mine = set(cells)
    failures += boxed(world, cell, fp, x, y, rot, mine, layers, owners)
    alternatives = world.tables().alternatives
    for layer in layers:
        touched = sorted(
            {
                (other_id, pin_id)
                for xy in mine
                for other_id, pin_id in alternatives.get(layer, {}).get(xy, ())
                if other_id != cell.id and other_id in world.placements
            }
        )
        for other_id, pin_id in touched:
            open_cells = [attach for _, attach in world.open_ports(other_id, pin_id)]
            covered = [attach for attach in open_cells if attach in mine]
            if covered and all(
                attach in mine or not _free(world, layer, attach)
                for attach in open_cells
            ):
                failures.append(
                    refusal(
                        "port_shut",
                        cell.id,
                        f"covers {other_id}.{pin_id}'s attach cell {covered[0]}",
                    )
                )
                break
    return failures


def _shut_by(
    world: Any,
    layer: str,
    attach: XY,
    owners: dict[str, dict[XY, str]],
    cell_id: str,
    pin: Any,
) -> str | None:
    """Why the attach cell is closed to the pin, or None when it is open."""
    if not world.in_grid(attach):
        return f"attaches at {attach}, outside the grid"
    owner = owners.get(layer, {}).get(attach)
    if owner is not None and not _same_net(world, owner, cell_id, pin.id):
        return f"attaches at {attach}, the attach cell of a pin of {owner}"
    for holder in world.kernel.holders_at(layer, attach):
        if not _connects(world, holder, attach, cell_id, pin):
            return f"attaches at {attach}, held by {holder}"
    return None


def _free(world: Any, layer: str, xy: XY) -> bool:
    """Whether no footprint stands on the cell."""
    return all(holder_kind(h)[0] != "cell" for h in world.kernel.holders_at(layer, xy))


POCKET = 12


def boxed(
    world: Any,
    cell: Any,
    fp: Footprint,
    x: int,
    y: int,
    rot: int,
    mine: set[XY],
    layers: tuple[str, ...],
    owners: dict[str, dict[XY, str]],
) -> list[Refusal]:
    """Every open attach cell of a net with an unplaced pin keeps a pocket; the new cell's own pins count.

    Only attach cells touching the new footprint, and the new cell's own, can lose their pocket
    to this placement, so only those are searched.
    """
    open_cells: dict[str, dict[XY, str]] = {
        layer: dict(found) for layer, found in owners.items()
    }
    own: dict[tuple[str, str], list[XY]] = {}
    for pin in world.netlist.pins_of(cell.id):
        options = options_at(fp, pin, x, y, rot)
        net_id = world.net_of(cell.id, pin.id)
        if not options or net_id is None:
            continue
        layer = world.carrier_layer(pin.carrier)
        if len(options) == 1:
            open_cells.setdefault(layer, {})[options[0][1]] = net_id
        own[(layer, net_id)] = [attach for _, attach, _ in options]
    halo = {
        (cx + dx, cy + dy) for cx, cy in mine for dx in (-1, 0, 1) for dy in (-1, 0, 1)
    }
    failures: list[Refusal] = []
    for layer in layers:
        pockets: list[tuple[str, list[XY]]] = [
            (net_id, [attach])
            for attach, net_id in open_cells.get(layer, {}).items()
            if attach in halo and (layer, net_id) not in own
        ]
        pockets += [
            (net_id, cells)
            for (own_layer, net_id), cells in own.items()
            if own_layer == layer
        ]
        for net_id, cells in pockets:
            net = world.netlist.nets[net_id]
            if all(r.cell == cell.id or r.cell in world.placements for r in net.pins()):
                continue
            exits = (
                _exits(world, layer, attach, mine, open_cells.get(layer, {}), net)
                for attach in cells
            )
            if all(found < POCKET for found in exits):
                failures.append(
                    refusal(
                        "port_shut",
                        cell.id,
                        f"boxes in the attach cell {cells[0]} of {net_id}",
                    )
                )
                break
    return failures


def _exits(
    world: Any,
    layer: str,
    xy: XY,
    mine: set[XY],
    open_cells: dict[XY, str],
    net: Any,
) -> int:
    """Cells reachable from ``xy`` through passable cells, counted up to ``POCKET``."""
    seen = {xy}
    frontier = [xy]
    while frontier and len(seen) <= POCKET:
        cx, cy = frontier.pop()
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            nxt = (cx + dx, cy + dy)
            if nxt in seen or not world.in_grid(nxt) or nxt in mine:
                continue
            other = open_cells.get(nxt)
            if other is not None and other != net.id:
                continue
            if _passable(world, layer, nxt, net):
                seen.add(nxt)
                frontier.append(nxt)
    return len(seen) - 1


def _passable(world: Any, layer: str, xy: XY, net: Any) -> bool:
    for holder in world.kernel.holders_at(layer, xy):
        kind, ref = holder_kind(holder)
        if kind == "cell":
            return False
        if kind == "wire" and ref != net.id:
            other = world.netlist.nets[ref]
            if (
                world.physics.carriers.crossing(net.carrier, other.carrier).mode
                == "forbidden"
            ):
                return False
    return True


def _connects(world: Any, holder: str, attach: XY, cell_id: str, pin: Any) -> bool:
    """Whether the holder of an attach cell connects the pin instead of shutting it: the pin's own net, a unit of it that carries the pin's carrier, a reservation for that carrier, another net's wire the pin's own may cross there, or a field emitter the route will displace."""
    kind, ref = holder_kind(holder)
    if kind == "unit":
        unit = world.units[ref]
        if unit.owner.startswith("field:"):
            return True
        owner = unit.owner.removeprefix("net:")
        return (
            owner in world.netlist.nets
            and _same_net(world, owner, cell_id, pin.id)
            and world.physics.carriers.transfers_through(unit.kind, pin.carrier)
        )
    if kind == "wire":
        if any(
            r.cell == cell_id and r.pin == pin.id
            for r in world.netlist.nets[ref].pins()
        ):
            return True
        layer = world.carrier_layer(pin.carrier)
        return crossable(world, layer, pin.carrier, ref, attach)
    if kind == "reserve":
        return world.reservations[ref].carrier == pin.carrier
    return False


def _same_net(world: Any, net_id: str, cell_id: str, pin_id: str) -> bool:
    return world.net_of(cell_id, pin_id) == net_id


def cover(world: Any, cell: Any, cells: tuple[XY, ...]) -> Refusal | None:
    """Ask the cover planner for the cell's needs and confirm every need is reached."""
    needs = world.physics.fields.needs(cell)
    if not needs:
        return None
    emitters = {e.kind: e for e in world.physics.fields.emitters()}
    for kind in needs:
        if kind not in emitters:
            return refusal(
                "field", cell.id, f"needs {kind!r}, which no emitter provides"
            )
    wanted = {kind: cells for kind in needs}
    for spot in world.physics.fields.cover(world, wanted):
        placed = world.place_unit(spot)
        if placed is not None:
            return refusal(
                "field",
                cell.id,
                f"cannot place an emitter for {spot.kind}: {placed.detail}",
            )
    for kind in needs:
        covered = world.field_coverage(kind)
        hit = (
            any(c in covered for c in cells)
            if emitters[kind].reach.partial
            else all(c in covered for c in cells)
        )
        if not hit:
            return refusal("field", cell.id, f"no emitter covers its need for {kind!r}")
    return None


__all__ = ["cover", "inspect", "port_shut", "refusal"]
