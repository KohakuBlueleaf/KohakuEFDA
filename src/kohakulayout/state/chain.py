"""The placement failure chain: what a placement must pass before the world holds it.

Every check names its stage from the chain (legal, region, overlap, port_shut, field);
the physics orders them through ``diagnose``.
"""

from typing import Any

from kohakulayout.ir import Footprint, PinRef, Refusal
from kohakulayout.ir.geometry import XY, attach_cell
from kohakulayout.physics.protocol import Occupant
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
) -> tuple[list[Refusal], list[str]]:
    """Every failure before occupancy, and the wires the placement may rip and re-route."""
    failures: list[Refusal] = []
    if rot not in fp.rotations:
        failures.append(refusal("legal", cell.id, f"rotation r{rot} is not allowed"))
    if not all(world.in_grid(c) for c in cells):
        failures.append(refusal("region", cell.id, "leaves the grid"))
    elif not all(world.in_build(c) for c in cells):
        failures.append(refusal("region", cell.id, "outside the build region"))
    occupant = Occupant(kind="cell", id=cell.id)
    ripped: list[str] = []
    for layer in layers:
        for xy in cells:
            blocker = world.may_occupy(layer, xy, occupant)
            if blocker is None:
                continue
            kind, ref = holder_kind(blocker)
            if kind == "wire" and world.router is not None:
                if ref not in ripped:
                    ripped.append(ref)
                continue
            failures.append(
                refusal("overlap", cell.id, f"{blocker} holds {xy} on {layer}")
            )
            break
    failures += port_shut(world, cell, fp, x, y, rot, cells, layers)
    return failures, ripped


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
    """The cell's own attach cells must be open, and it must cover no other open attach cell."""
    failures: list[Refusal] = []
    owners = world.open_attach_owners() if owners is None else owners
    for pin in world.netlist.pins_of(cell.id):
        port = fp.port(pin.ports[0]) if pin.ports else None
        if port is None:
            continue
        ax, ay = attach_cell(fp.width, fp.height, port.side, port.offset, rot)
        attach = (x + ax, y + ay)
        layer = world.carrier_layer(pin.carrier)
        if not world.in_grid(attach):
            failures.append(
                refusal(
                    "port_shut",
                    cell.id,
                    f"pin {pin.id} attaches at {attach}, outside the grid",
                )
            )
            continue
        owner = owners.get(layer, {}).get(attach)
        if owner is not None and not _same_net(world, owner, cell.id, pin.id):
            failures.append(
                refusal(
                    "port_shut",
                    cell.id,
                    f"pin {pin.id} attaches at {attach}, the attach cell of a pin of {owner}",
                )
            )
            continue
        for holder in world.kernel.holders_at(layer, attach):
            if _connects(world, holder, cell.id, pin):
                continue
            failures.append(
                refusal(
                    "port_shut",
                    cell.id,
                    f"pin {pin.id} attaches at {attach}, held by {holder}",
                )
            )
            break
    mine = set(cells)
    failures += boxed(world, cell, fp, x, y, rot, mine, layers, owners)
    for other_id in world.placements:
        for pin_id, attach in world.attach_cells(other_id).items():
            pin = world.netlist.pin(PinRef(cell=other_id, pin=pin_id))
            if (
                attach not in mine
                or pin is None
                or world.carrier_layer(pin.carrier) not in layers
                or _routed(world, other_id, pin_id)
            ):
                continue
            failures.append(
                refusal(
                    "port_shut",
                    cell.id,
                    f"covers {other_id}.{pin_id}'s attach cell {attach}",
                )
            )
            break
    return failures


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
    own: set[tuple[str, XY]] = set()
    for pin in world.netlist.pins_of(cell.id):
        port = fp.port(pin.ports[0]) if pin.ports else None
        net = _net_of(world, cell.id, pin.id)
        if port is None or net is None:
            continue
        ax, ay = attach_cell(fp.width, fp.height, port.side, port.offset, rot)
        layer = world.carrier_layer(pin.carrier)
        open_cells.setdefault(layer, {})[(x + ax, y + ay)] = net.id
        own.add((layer, (x + ax, y + ay)))
    halo = {
        (cx + dx, cy + dy) for cx, cy in mine for dx in (-1, 0, 1) for dy in (-1, 0, 1)
    }
    failures: list[Refusal] = []
    for layer in layers:
        for attach, net_id in open_cells.get(layer, {}).items():
            if attach not in halo and (layer, attach) not in own:
                continue
            net = world.netlist.nets[net_id]
            if all(r.cell == cell.id or r.cell in world.placements for r in net.pins()):
                continue
            if _exits(world, layer, attach, mine, open_cells[layer], net) < POCKET:
                failures.append(
                    refusal(
                        "port_shut",
                        cell.id,
                        f"boxes in the attach cell {attach} of {net_id}",
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


def _net_of(world: Any, cell_id: str, pin_id: str) -> Any:
    for net in world.netlist.nets.values():
        if any(r.cell == cell_id and r.pin == pin_id for r in net.pins()):
            return net
    return None


def _connects(world: Any, holder: str, cell_id: str, pin: Any) -> bool:
    """Whether the holder of an attach cell connects the pin instead of shutting it."""
    kind, ref = holder_kind(holder)
    if kind == "unit":
        return world.physics.carriers.transfers_through(
            world.units[ref].kind, pin.carrier
        )
    if kind == "wire":
        return any(
            r.cell == cell_id and r.pin == pin.id
            for r in world.netlist.nets[ref].pins()
        )
    if kind == "reserve":
        return world.reservations[ref].carrier == pin.carrier
    return False


def _same_net(world: Any, net_id: str, cell_id: str, pin_id: str) -> bool:
    return any(
        r.cell == cell_id and r.pin == pin_id for r in world.netlist.nets[net_id].pins()
    )


def _routed(world: Any, cell_id: str, pin_id: str) -> bool:
    return any(
        n.id in world.wires
        for n in world.nets_of(cell_id)
        if any(r.cell == cell_id and r.pin == pin_id for r in n.pins())
    )


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
