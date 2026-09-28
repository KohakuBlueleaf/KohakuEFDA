"""The project netlist as a framework problem: cells with their pins, lanes as nets, groups, the basement.

A project net joins every out pin of an item to every in pin; the synth pairs them into
lanes as a staircase (the small sources one to a sink in turn, then the largest sinks
first, each filled from the largest sources in order, so a sink takes from few sources
and a source feeds few sinks). Each connected set of lanes becomes one framework net,
so a source feeding two sinks is a tree the router splits, and a sink fed by two sources
a tree it merges; a pair on its own is one wire. Under ``OWN_PORTS`` a belt net is one
per source pin instead, a tree that only splits, and a sink that several source pins
reach takes each on a pin of its own (a copy of the sink pin on the same ports): the
community's model, worth its belts once the plan pairs pins whole.
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
from kohakuefda.synth.hierarchy import hierarchical_of
from kohakuefda.synth.tiles import with_macros
from kohakulayout.ir import Cell, Constraint, Group, Net, Netlist, Pin, PinRef, Problem

UNPOWERED_KINDS = frozenset({"core", "pylon", "entry"})
CAPACITY = {"belt": BELT_PER_MIN, "pipe": PIPE_PER_MIN}
POWER = "power"
Lane = tuple[str, str, str, str, Fraction]
PinKey = tuple[str, str]


CLOSING = True
OWN_PORTS = False
PAIR_CELLS = False
COPY = "__dup"
Copy = tuple[str, str, Fraction]


def kl_id(pin_id: str) -> str:
    """A project pin id as a framework identifier: each colon becomes a double underscore."""
    return pin_id.replace(":", "__")


def project_pin_id(pin_id: str) -> str:
    """The project pin behind a framework pin id, a copy's ``COPY`` suffix dropped."""
    return pin_id.split(COPY, 1)[0].replace("__", ":")


def constraint_kind(cell: CellInstance) -> str:
    """The project constraint, with a grouped cell's kind named so the pack hands out its anchors."""
    if cell.constraint != "free":
        return cell.constraint
    if cell.group == BUS_GROUP:
        return SEAT if cell.kind in BRICK_KINDS else CLUSTER
    if cell.kind == ZONE_KIND:
        return ZONE_KIND
    return "free"


def cell_of(
    cell: CellInstance,
    dataset: Dataset,
    library: dict[str, Any],
    copies: list[Copy] | None = None,
) -> Cell:
    """The framework cell: the project pins, plus a copy of a sink pin per extra
    source pin that reaches it (``copies``: copy id, pin id, rate), on the same ports.
    """
    fp = library[cell.machine_id]
    machine = dataset.machines.get(cell.machine_id)
    powered = (
        cell.kind not in UNPOWERED_KINDS and machine is not None and machine.needs_power
    )
    config: dict[str, str] = {}
    for placed in cell.machines:
        config.update(placed.config)
    base = {kl_id(p.id): p for p in cell.pins}
    extra = [(copy_id, base[pin_id], rate) for copy_id, pin_id, rate in copies or ()]
    pins = tuple(
        Pin(
            id=kl_id(pin.id),
            direction=pin.direction,
            carrier=pin.kind,
            ports=ports_for(fp, pin),
        )
        for pin in cell.pins
    ) + tuple(
        Pin(
            id=copy_id,
            direction=pin.direction,
            carrier=pin.kind,
            ports=ports_for(fp, pin),
        )
        for copy_id, pin, _ in extra
    )
    info: dict[str, Any] = {
        "machine": cell.machine_id,
        "power": machine.power if machine is not None else 0,
        "pins": [pin_fact(kl_id(p.id), p.item_id, p.rate) for p in cell.pins]
        + [pin_fact(copy_id, p.item_id, rate) for copy_id, p, rate in extra],
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
    """A staircase: the sources with less than half the smallest demand go one to a sink in turn, then the largest sinks first are each filled from the largest sources in order, a source's flow contiguous over the sinks, so a sink takes from few sources and a source feeds few sinks."""
    room: dict[PinKey, Fraction] = {}
    for key, rate in sources:
        room[key] = room.get(key, Fraction(0)) + rate
    demand: dict[PinKey, Fraction] = {}
    for sink, rate in sorted(sinks, key=lambda s: -s[1]):
        demand[sink] = demand.get(sink, Fraction(0)) + rate
    out: list[tuple[PinKey, PinKey, Fraction]] = []
    if not demand:
        return out
    order = sorted(room, key=lambda k: -room[k])
    least = min(demand.values())
    small = [k for k in order if room[k] * 2 < least]
    targets = list(demand)
    for index, key in enumerate(small):
        sink = targets[index % len(targets)]
        take = min(room[key], demand[sink])
        if take > 0:
            out.append((key, sink, take))
            room[key] -= take
            demand[sink] -= take
    large = [k for k in order if k not in small]
    at = 0
    for sink in targets:
        while demand[sink] > 0 and at < len(large):
            key = large[at]
            take = min(room[key], demand[sink])
            if take > 0:
                out.append((key, sink, take))
                room[key] -= take
                demand[sink] -= take
            if room[key] <= 0:
                at += 1
    return out


def closing(
    sources: list[tuple[PinKey, Fraction]],
    sinks: list[tuple[PinKey, Fraction]],
    feeders: dict[str, set[str]],
) -> list[tuple[PinKey, PinKey, Fraction]]:
    """Best fit that first gives a sink, whole, a source its own cell feeds, so a return flow
    closes its loop on the machine it came from; the rest as ``assign``."""
    room = dict(sources)
    demand = dict(sinks)
    out: list[tuple[PinKey, PinKey, Fraction]] = []
    for sink, need in sorted(sinks, key=lambda s: -s[1]):
        holders = [
            k
            for k, _ in sources
            if room[k] >= need and sink[0] in feeders.get(k[0], set())
        ]
        if holders:
            best = min(holders, key=lambda k: room[k])
            out.append((best, sink, need))
            room[best] -= need
            demand[sink] -= need
    rest_s = [(k, room[k]) for k, _ in sources if room[k] > 0]
    rest_k = [(k, demand[k]) for k, _ in sinks if demand[k] > 0]
    return out + assign(rest_s, rest_k)


def lanes_of(
    net: NetSpec,
    units: dict[str, str | None] | None = None,
    feeders: dict[str, set[str]] | None = None,
) -> list[tuple[PinKey, PinKey, Fraction]]:
    """The lanes of one project net: a pipe net with several sources and several sinks is a trunk from the fullest source to the fullest sink, the other sources joining that sink and that source branching to the other sinks; every other net is best-fit pairs (``closing`` for a belt net when ``feeders`` names each cell's suppliers; a pipe carries no loop worth closing), a belt net paired cell to cell first and then spread over the cells' pins (``PAIR_CELLS``), the pins of one repeat unit paired among themselves first and, when the pins nothing inside touched can carry the rest, only those feeding across units, so a lane never straddles a unit."""
    sources = [((r.cell_id, r.pin_id), r.rate) for r in net.sources if r.rate > 0]
    sinks = [((r.cell_id, r.pin_id), r.rate) for r in net.sinks if r.rate > 0]
    if net.kind == "pipe" and len(sources) > 1 and len(sinks) > 1:
        root, root_rate = max(sources, key=lambda s: s[1])
        main, _ = max(sinks, key=lambda s: s[1])
        lanes = [(root, main, root_rate)]
        lanes += [(key, main, rate) for key, rate in sources if key != root]
        lanes += [(root, key, rate) for key, rate in sinks if key != main]
        return lanes

    def pair(
        s: list[tuple[PinKey, Fraction]], k: list[tuple[PinKey, Fraction]]
    ) -> list[tuple[PinKey, PinKey, Fraction]]:
        if PAIR_CELLS and net.kind != "pipe":
            cells_s, cells_k = by_cell(s), by_cell(k)
            paired = (
                closing(cells_s, cells_k, feeders)
                if feeders
                else assign(cells_s, cells_k)
            )
            return spread(paired, s, k, BELT_PER_MIN)
        if feeders and net.kind != "pipe":
            return closing(s, k, feeders)
        return assign(s, k)

    if not units:
        return pair(sources, sinks)
    lanes: list[tuple[PinKey, PinKey, Fraction]] = []
    room = dict(sources)
    demand = dict(sinks)
    homes = {u for key, _ in sources for u in [units.get(key[0])] if u is not None}
    for unit in sorted(homes):
        mine_s = [(k, r) for k, r in sources if units.get(k[0]) == unit and room[k] > 0]
        mine_k = [(k, r) for k, r in sinks if units.get(k[0]) == unit and demand[k] > 0]
        for source, sink, rate in pair(mine_s, mine_k):
            lanes.append((source, sink, rate))
            room[source] -= rate
            demand[sink] -= rate
    untouched_s = [(k, room[k]) for k, r in sources if room[k] == r]
    untouched_k = [(k, demand[k]) for k, r in sinks if demand[k] == r]
    rest_s = [(k, room[k]) for k, _ in sources if room[k] > 0]
    rest_k = [(k, demand[k]) for k, _ in sinks if demand[k] > 0]
    if sum((r for _, r in untouched_s), Fraction(0)) >= sum(
        (r for _, r in untouched_k), Fraction(0)
    ) and len(untouched_k) == len(rest_k):
        return lanes + pair(untouched_s, untouched_k)
    return lanes + pair(rest_s, rest_k)


def by_cell(refs: list[tuple[PinKey, Fraction]]) -> list[tuple[PinKey, Fraction]]:
    """The pins' rates summed per cell, as one pseudo pin ``(cell, "")`` each, in first-seen order."""
    total: dict[str, Fraction] = {}
    for (cell, _), rate in refs:
        total[cell] = total.get(cell, Fraction(0)) + rate
    return [((cell, ""), rate) for cell, rate in total.items()]


def spread(
    cell_lanes: list[tuple[PinKey, PinKey, Fraction]],
    sources: list[tuple[PinKey, Fraction]],
    sinks: list[tuple[PinKey, Fraction]],
    capacity: Fraction,
) -> list[tuple[PinKey, PinKey, Fraction]]:
    """Each cell-to-cell lane on the pins of its cells: the pin with the most room left at
    either end, no pin past ``capacity`` while another has room, so a pair of machines
    exchanges one belt from one port when the belt carries it (LOG-10: a facility sends to
    the outlet whose downstream is least loaded)."""
    room: dict[PinKey, Fraction] = {key: capacity for key, _ in [*sources, *sinks]}
    pins: dict[str, list[PinKey]] = {}
    for key, _ in [*sources, *sinks]:
        pins.setdefault(key[0], []).append(key)
    out: list[tuple[PinKey, PinKey, Fraction]] = []
    for (source_cell, _), (sink_cell, _), rate in cell_lanes:
        left = rate
        while left > 0:
            source = max(pins[source_cell], key=lambda k: room[k])
            sink = max(pins[sink_cell], key=lambda k: room[k])
            take = min(
                left,
                room[source] if room[source] > 0 else left,
                room[sink] if room[sink] > 0 else left,
            )
            out.append((source, sink, take))
            room[source] -= take
            room[sink] -= take
            left -= take
    return out


def feeders_of(netlist: ProjectNetlist) -> dict[str, set[str]]:
    """Each cell's suppliers: the cells whose pins source a net it sinks."""
    out: dict[str, set[str]] = {}
    for spec in netlist.nets:
        cells = {r.cell_id for r in spec.sources if r.rate > 0}
        for ref in spec.sinks:
            out.setdefault(ref.cell_id, set()).update(cells)
    return out


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


def by_source(
    lanes: list[tuple[PinKey, PinKey, Fraction]],
) -> list[list[tuple[PinKey, PinKey, Fraction]]]:
    """Lanes grouped by their source pin, in first-seen order: each group one belt tree that only splits."""
    groups: dict[PinKey, list[tuple[PinKey, PinKey, Fraction]]] = {}
    for lane in lanes:
        groups.setdefault(lane[0], []).append(lane)
    return list(groups.values())


def split_lanes(
    spec: NetSpec, lanes: list[tuple[PinKey, PinKey, Fraction]]
) -> list[list[tuple[PinKey, PinKey, Fraction]]]:
    """The framework nets of a project net: a belt net one per source pin when
    ``OWN_PORTS`` (a sink several source pins reach takes each on a port of its own),
    else the connected sets of its lanes."""
    if OWN_PORTS and spec.kind != "pipe":
        return by_source(lanes)
    return components(lanes)


def nets_of(netlist: ProjectNetlist) -> tuple[dict[str, Net], dict[str, list[Copy]]]:
    """The framework nets, and per cell the sink pins to copy for the extra source pins that reach them."""
    out: dict[str, Net] = {}
    copies: dict[str, list[Copy]] = {}
    units = {c.id: c.unit for c in netlist.cells}
    feeders = feeders_of(netlist) if CLOSING else None
    for spec in netlist.nets:
        reached: dict[PinKey, int] = {}
        for index, lanes in enumerate(
            split_lanes(spec, lanes_of(spec, units, feeders))
        ):
            taken: dict[PinKey, Fraction] = {}
            for _, sink, rate in lanes:
                taken[sink] = taken.get(sink, Fraction(0)) + rate
            names: dict[PinKey, str] = {}
            for sink, rate in taken.items():
                n = reached.get(sink, 0)
                names[sink] = kl_id(sink[1]) + (f"{COPY}{n}" if n else "")
                if n:
                    copies.setdefault(sink[0], []).append(
                        (names[sink], kl_id(sink[1]), rate)
                    )
                reached[sink] = n + 1
            group = [(s, (t[0], names[t]), rate) for s, t, rate in lanes]
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
            load: dict[PinRef, Fraction] = {}
            for source, _, rate in group:
                ref = PinRef(cell=source[0], pin=kl_id(source[1]))
                load[ref] = load.get(ref, Fraction(0)) + rate
            sources.sort(key=lambda ref: -load[ref])
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
    return out, copies


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
    dataset: Dataset,
    netlist: ProjectNetlist,
    board: Board | None = None,
    macros: dict[str, Any] | None = None,
) -> Problem:
    """The framework problem for a project netlist on its basement; with ``macros`` (per
    module id) the netlist is folded into modules and its instances stand on them."""
    board = board if board is not None else board_of(dataset, netlist.scenario)
    library = library_of(dataset, netlist.cells)
    physics = EndfieldPhysics()
    params = params_of(board)
    nets, copies = nets_of(netlist)
    kl_netlist = Netlist(
        pack=physics.id,
        library=library,
        cells={
            c.id: cell_of(c, dataset, library, copies.get(c.id)) for c in netlist.cells
        },
        nets=nets,
        groups=groups_of(netlist.cells),
        attrs={
            NAMESPACE: {
                "dataset": netlist.dataset_version,
                "region": str(netlist.scenario.basement.region.value),
                "basement": netlist.scenario.basement.basement_id,
                "level": netlist.scenario.basement.level,
                "depot_level": netlist.scenario.basement.depot_level,
                "entry": ENTRY,
                "links": [f"{k.inlet}:{k.outlet}" for k in netlist.links],
            }
        },
    )
    if macros is not None:
        kl_netlist = with_macros(hierarchical_of(netlist, kl_netlist), macros)
    return Problem(
        physics=physics.ref,
        fabric=physics.fabric(params),
        netlist=kl_netlist,
        params=params,
    )


__all__ = [
    "COPY",
    "OWN_PORTS",
    "assign",
    "busiest",
    "by_source",
    "cell_of",
    "closing",
    "components",
    "constraint_kind",
    "feeders_of",
    "groups_of",
    "kl_id",
    "lanes_of",
    "nets_of",
    "params_of",
    "problem_of",
    "project_pin_id",
    "split_lanes",
]
