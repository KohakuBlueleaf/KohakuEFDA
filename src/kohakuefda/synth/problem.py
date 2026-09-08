"""The project netlist as a framework problem: cells with their pins, lanes as nets, groups, the basement.

A project net joins every out pin of an item to every in pin; the synth pairs them into
lanes (a sink whole from the source with the least room, else split). Each connected set
of lanes becomes one framework net, so a source feeding two sinks is a tree the router
splits, and a sink fed by two sources a tree it merges; a pair on its own is one wire.
"""

from fractions import Fraction
from typing import Any

from kohakuefda.layout.board import Board, board_of
from kohakuefda.model.cells import CellInstance, NetSpec
from kohakuefda.model.cells import Netlist as ProjectNetlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.physics import EndfieldPhysics
from kohakuefda.physics.boundaries import (
    BRICK_KINDS,
    BUS_GROUP,
    CLUSTER,
    SEAT,
    ZONE_KIND,
)
from kohakuefda.physics.fabric import BELT_PER_MIN, NAMESPACE, PIPE_PER_MIN
from kohakuefda.physics.facts import (
    cell_text,
    lane_fact,
    pin_fact,
    rate_text,
    slot_text,
)
from kohakuefda.synth.footprints import ENTRY, library_of, ports_for
from kohakulayout.ir import Cell, Constraint, Group, Net, Netlist, Pin, PinRef, Problem

UNPOWERED_KINDS = frozenset({"core", "pylon", "entry"})
CAPACITY = {"belt": BELT_PER_MIN, "pipe": PIPE_PER_MIN}
POWER = "power"
Lane = tuple[str, str, str, str, Fraction]
PinKey = tuple[str, str]


def kl_id(pin_id: str) -> str:
    """A project pin id as a framework identifier: each colon becomes a double underscore."""
    return pin_id.replace(":", "__")


def project_pin_id(pin_id: str) -> str:
    return pin_id.replace("__", ":")


def constraint_kind(cell: CellInstance) -> str:
    """The project constraint, with a grouped cell's kind named so the pack hands out its anchors."""
    if cell.constraint != "free":
        return cell.constraint
    if cell.group == BUS_GROUP:
        return SEAT if cell.kind in BRICK_KINDS else CLUSTER
    if cell.kind == ZONE_KIND:
        return ZONE_KIND
    return "free"


def cell_of(cell: CellInstance, dataset: Dataset, library: dict[str, Any]) -> Cell:
    fp = library[cell.machine_id]
    machine = dataset.machines.get(cell.machine_id)
    powered = (
        cell.kind not in UNPOWERED_KINDS and machine is not None and machine.needs_power
    )
    config: dict[str, str] = {}
    for placed in cell.machines:
        config.update(placed.config)
    pins = tuple(
        Pin(
            id=kl_id(pin.id),
            direction=pin.direction,
            carrier=pin.kind,
            ports=ports_for(fp, pin),
        )
        for pin in cell.pins
    )
    info: dict[str, Any] = {
        "machine": cell.machine_id,
        "power": machine.power if machine is not None else 0,
        "pins": [pin_fact(kl_id(p.id), p.item_id, p.rate) for p in cell.pins],
    }
    if cell.recipe_id:
        info["recipe"] = cell.recipe_id
    if cell.env:
        info["env"] = cell.env
    if config:
        info["config"] = [f"{k}:{v}" for k, v in sorted(config.items())]
    return Cell(
        id=cell.id,
        kind=cell.kind,
        footprint=fp.id,
        pins=pins,
        constraint=Constraint(kind=constraint_kind(cell)),
        group=cell.group,
        needs=(POWER,) if powered else (),
        attrs={NAMESPACE: info},
    )


def assign(
    sources: list[tuple[PinKey, Fraction]], sinks: list[tuple[PinKey, Fraction]]
) -> list[tuple[PinKey, PinKey, Fraction]]:
    """Best fit: the largest sinks first, each whole from the source with the least room that holds it, else split."""
    room: dict[PinKey, Fraction] = {}
    for key, rate in sources:
        room[key] = room.get(key, Fraction(0)) + rate
    out: list[tuple[PinKey, PinKey, Fraction]] = []
    for sink, demand in sorted(sinks, key=lambda s: -s[1]):
        holders = [k for k, left in room.items() if left >= demand]
        if holders:
            best = min(holders, key=lambda k: room[k])
            out.append((best, sink, demand))
            room[best] -= demand
            continue
        remaining = demand
        for key in list(room):
            if remaining <= 0:
                break
            take = min(room[key], remaining)
            if take > 0:
                out.append((key, sink, take))
                room[key] -= take
                remaining -= take
    return out


def lanes_of(net: NetSpec) -> list[tuple[PinKey, PinKey, Fraction]]:
    """The lanes of one project net: best-fit pairs of a source and a sink, belts and pipes alike."""
    sources = [((r.cell_id, r.pin_id), r.rate) for r in net.sources if r.rate > 0]
    sinks = [((r.cell_id, r.pin_id), r.rate) for r in net.sinks if r.rate > 0]
    return assign(sources, sinks)


def components(
    lanes: list[tuple[PinKey, PinKey, Fraction]],
) -> list[list[tuple[PinKey, PinKey, Fraction]]]:
    """Lanes grouped by the pins they share, in first-seen order."""
    parent: dict[PinKey, PinKey] = {}

    def find(key: PinKey) -> PinKey:
        while parent.setdefault(key, key) != key:
            key = parent[key]
        return key

    for source, sink, _ in lanes:
        parent[find(source)] = find(sink)
    groups: dict[PinKey, list[tuple[PinKey, PinKey, Fraction]]] = {}
    for lane in lanes:
        groups.setdefault(find(lane[0]), []).append(lane)
    return list(groups.values())


def busiest(group: list[tuple[PinKey, PinKey, Fraction]]) -> Fraction:
    """The rate on the fullest terminal of a lane set: what one wire of the tree carries at most."""
    load: dict[PinKey, Fraction] = {}
    for source, sink, rate in group:
        load[source] = load.get(source, Fraction(0)) + rate
        load[sink] = load.get(sink, Fraction(0)) + rate
    return max(load.values(), default=Fraction(0))


def nets_of(netlist: ProjectNetlist) -> dict[str, Net]:
    out: dict[str, Net] = {}
    for spec in netlist.nets:
        for index, group in enumerate(components(lanes_of(spec))):
            sources: list[PinRef] = []
            sinks: list[PinRef] = []
            for source, sink, _ in group:
                ref = PinRef(cell=source[0], pin=kl_id(source[1]))
                if ref not in sources:
                    sources.append(ref)
                ref = PinRef(cell=sink[0], pin=kl_id(sink[1]))
                if ref not in sinks:
                    sinks.append(ref)
            net_id = f"{spec.id}_{index}"
            out[net_id] = Net(
                id=net_id,
                kind="lane",
                carrier=spec.kind,
                rate=min(busiest(group), CAPACITY[spec.kind]),
                sources=tuple(sources),
                sinks=tuple(sinks),
                attrs={
                    NAMESPACE: {
                        "item": spec.item_id,
                        "net": spec.id,
                        "via_depot_ok": spec.via_depot_ok,
                        "rate": rate_text(busiest(group)),
                        "lanes": [
                            lane_fact((s[0], kl_id(s[1])), (t[0], kl_id(t[1])), rate)
                            for s, t, rate in group
                        ],
                    }
                },
            )
    return out


def groups_of(cells: list[CellInstance]) -> dict[str, Group]:
    members: dict[str, list[str]] = {}
    for cell in cells:
        if cell.group:
            members.setdefault(cell.group, []).append(cell.id)
    return {name: Group(id=name, members=tuple(ids)) for name, ids in members.items()}


def params_of(board: Board) -> dict[str, Any]:
    """The basement as fabric params; fixed bus cells beyond the grid and empty lists are left out."""
    out: dict[str, Any] = {
        "square": list(board.square),
        "ring": board.ring,
        "entry_area": list(board.entry_area),
    }
    width, height = board.grid
    fixed = sorted(c for c in board.fixed if 0 <= c[0] < width and 0 <= c[1] < height)
    if fixed:
        out["fixed"] = [cell_text(x, y) for x, y in fixed]
    if board.slots:
        out["slots"] = [slot_text(s.x, s.y, s.side.value) for s in board.slots]
    return out


def problem_of(
    dataset: Dataset, netlist: ProjectNetlist, board: Board | None = None
) -> Problem:
    """The framework problem for a project netlist on its basement."""
    board = board if board is not None else board_of(dataset, netlist.scenario)
    library = library_of(dataset, netlist.cells)
    physics = EndfieldPhysics()
    params = params_of(board)
    kl_netlist = Netlist(
        pack=physics.id,
        library=library,
        cells={c.id: cell_of(c, dataset, library) for c in netlist.cells},
        nets=nets_of(netlist),
        groups=groups_of(netlist.cells),
        attrs={
            NAMESPACE: {
                "dataset": netlist.dataset_version,
                "region": str(netlist.scenario.basement.region.value),
                "basement": netlist.scenario.basement.basement_id,
                "level": netlist.scenario.basement.level,
                "depot_level": netlist.scenario.basement.depot_level,
                "entry": ENTRY,
            }
        },
    )
    return Problem(
        physics=physics.ref,
        fabric=physics.fabric(params),
        netlist=kl_netlist,
        params=params,
    )


__all__ = [
    "assign",
    "busiest",
    "cell_of",
    "components",
    "constraint_kind",
    "groups_of",
    "kl_id",
    "lanes_of",
    "nets_of",
    "params_of",
    "problem_of",
    "project_pin_id",
]
