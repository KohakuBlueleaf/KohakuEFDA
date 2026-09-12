"""The world's side of the native twin: its records mirrored into the twin, and the routing
pass, the placement attempt and the admission check answered there.

The twin receives the world's fixed records once and, before each call, what changed since
the last; every call undoes its writes. A refusal comes back as Python's would, with the unit
counter the Python path would leave; any other answer lets Python decide.
"""

import json
from typing import Any
from weakref import WeakKeyDictionary

from kohakulayout._rust_bridge import rust_admits, rust_attempt, rust_route_pass
from kohakulayout.ir import Placement, Refusal
from kohakulayout.physics.protocol import Occupant
from kohakulayout.state.attach import options_at
from kohakulayout.state.router.pathfinder import (
    MODES,
    register_regions,
    register_walls,
    unit_footprints,
)
from kohakulayout.state.router.protocol import refuse

KINDS: tuple[str, ...] = ("open", "routed", "ports")


class Mirror:
    """What the twin last received from one world."""

    def __init__(self) -> None:
        self.stamp: tuple[int, Any, Any] | None = None
        self.placements: dict[str, Any] = {}
        self.wires: dict[str, Any] = {}
        self.units: dict[str, Any] = {}
        self.entries: dict[str, list[tuple[str, str, Any]]] = {}
        self.others: set[str] = set()
        self.placing: tuple[str, ...] = ()
        self.keys: dict[str, tuple[str, str]] = {}
        self.order: list[str] = []
        self.costs: Any = None
        self.revision: int | None = None
        self.fixed: tuple[Any, int, int, str] | None = None


_MIRRORS: "WeakKeyDictionary[Any, Mirror]" = WeakKeyDictionary()


def occupant_of(key: str) -> Occupant:
    """The occupant an occupant key names, as ``Occupant.key`` writes it."""
    kind, _, rest = key.partition(":")
    if kind == "unit":
        return Occupant(kind="unit", unit_kind=rest or None)
    if kind in ("wire", "reserve"):
        return Occupant(kind=kind, carrier=rest or None)
    return Occupant(kind=kind)


def share_rows(
    world: Any, others: set[str], placing: tuple[str, ...]
) -> list[tuple[str, str, bool]]:
    """Whether each holder key may share a cell with a unit of each kind a route places."""
    return [
        (
            other,
            f"unit:{kind}",
            bool(
                world.share.may_share(occupant_of(other), occupant_of(f"unit:{kind}"))
            ),
        )
        for kind in placing
        for other in sorted(others)
    ]


def statics(world: Any, mirror: Mirror, router: Any) -> dict[str, Any]:
    """The world's fixed records for the twin."""
    carriers = []
    placing: set[str] = {fp.id for fp in unit_footprints(world)}
    for c in world.fabric.carriers:
        rule = world.physics.carriers.junction(c)
        repeater = world.physics.carriers.repeater(c)
        if repeater is not None:
            placing.add(repeater.id)
        carriers.append(
            {
                "id": c,
                "layer": world.carrier_layer(c),
                "junction": MODES.get(rule.mode, 1),
                "split": rule.split.id if rule.split is not None else None,
                "merge": rule.merge.id if rule.merge is not None else None,
                "run_limit": world.physics.carriers.run_limit(c),
                "repeater": repeater.id if repeater is not None else None,
            }
        )
    nets, pins = [], []
    for net in world.netlist.nets.values():
        nets.append(
            {
                "id": net.id,
                "carrier": net.carrier,
                "sources": [str(r) for r in net.sources],
                "sinks": [str(r) for r in net.sinks],
                "outside": net.outside is not None,
            }
        )
        for ref in net.pins():
            pin = world.netlist.pin(ref)
            pins.append(
                {
                    "id": str(ref),
                    "cell": ref.cell,
                    "pin": ref.pin,
                    "net": net.id,
                    "bound": pin is None or len(pin.ports) <= 1,
                }
            )
    fields = world.physics.fields
    native_fields = fields.native(world) if hasattr(fields, "native") else None
    if native_fields is not None:
        placing |= {s["kind"] for s in native_fields["sweeps"]}
    mirror.placing = tuple(sorted(placing))
    mirror.others = {"cell:", "unit:"} | {f"wire:{c}" for c in world.fabric.carriers}
    mirror.others |= {f"unit:{k}" for k in placing}
    kinds = sorted(set(world.library) | placing)
    build = world.fabric.regions.get("build")
    return {
        "nets": nets,
        "pins": pins,
        "footprints": [
            {
                "id": fp.id,
                "width": fp.width,
                "height": fp.height,
                "layer": fp.layer,
                "occludes": list(fp.occludes),
                "rotations": list(fp.rotations),
            }
            for fp in world.library.values()
        ],
        "share": share_rows(world, mirror.others, mirror.placing)
        + [
            (
                other,
                "cell:",
                bool(world.share.may_share(occupant_of(other), occupant_of("cell:"))),
            )
            for other in sorted(mirror.others)
        ],
        "carriers": carriers,
        "fields": native_fields,
        "policies": [
            (net.id, spec)
            for net in world.netlist.nets.values()
            if (spec := router.policy.native(world, net)) is not None
        ],
        "build": sorted(build.cells()) if build is not None else None,
        "cell_nets": [
            (cell_id, [n.id for n in world.nets_of(cell_id)])
            for cell_id in world.netlist.cells
        ],
        "cell_pins": [
            (cell_id, [(pin.id, pin.carrier) for pin in world.netlist.pins_of(cell_id)])
            for cell_id in world.netlist.cells
        ],
        "transfers": [
            (kind, c)
            for kind in kinds
            for c in world.fabric.carriers
            if world.physics.carriers.transfers_through(kind, c)
        ],
        "orders": [
            (net.id, data)
            for net in world.netlist.nets.values()
            if hasattr(router, "order_data")
            and (data := router.order_data(world, net)) is not None
        ],
        "needs": [
            (cell_id, list(fields.needs(cell)))
            for cell_id, cell in world.netlist.cells.items()
            if fields.needs(cell)
        ],
    }


def _wire(wire: Any) -> dict[str, Any]:
    return {
        "segments": [[seg.layer, seg.cells] for seg in wire.segments],
        "units": list(wire.units),
        "ports": list(wire.ports.items()),
    }


def _unit(unit: Any) -> dict[str, Any]:
    return {
        "kind": unit.kind,
        "footprint": unit.footprint,
        "x": unit.x,
        "y": unit.y,
        "rot": unit.rot,
        "owner": unit.owner,
    }


def _changed(current: dict[str, Any], sent: dict[str, Any], full: bool) -> list[str]:
    """The keys whose object is not the one sent, and the keys gone since."""
    keys = [k for k, v in current.items() if full or sent.get(k) is not v]
    keys += [k for k in sent if k not in current]
    return keys


_UNCHANGED: dict[str, Any] = {
    "full": False,
    "placements": [],
    "order": None,
    "wires": [],
    "units": [],
    "tables_full": False,
    "cells": [],
    "entries": [],
    "table_pins": [],
    "share": [],
}


def sync_doc(world: Any, mirror: Mirror, full: bool) -> dict[str, Any]:
    """The records changed since the last sync, or all; only the unit counter when none changed."""
    if (
        not full
        and mirror.revision == world.revision
        and not world._retable_all
        and not world._retabled
    ):
        return {**_UNCHANGED, "unit_seq": world._unit_seq}
    mirror.revision = world.revision
    placements = []
    for cell in _changed(world.placements, mirror.placements, full):
        placement = world.placements.get(cell)
        placements.append(
            (
                cell,
                (
                    None
                    if placement is None
                    else {
                        "x": placement.x,
                        "y": placement.y,
                        "rot": placement.rot,
                        "footprint": world.footprint_of(cell).id,
                        "choices": list(world.port_choices(cell).items()),
                    }
                ),
            )
        )
    order = list(world.placements)
    changed_order = full or order != mirror.order
    mirror.order = order
    wires = [
        (net, _wire(world.wires[net]) if net in world.wires else None)
        for net in _changed(world.wires, mirror.wires, full)
    ]
    units = [
        (uid, _unit(world.units[uid]) if uid in world.units else None)
        for uid in _changed(world.units, mirror.units, full)
    ]
    kinds = {f"unit:{u.kind}" for u in world.units.values()} - mirror.others
    mirror.others |= kinds
    share = share_rows(world, kinds, mirror.placing) if kinds else []
    tables = world._tables
    everything = full or world._retable_all
    nets = list(tables.entries) if everything else sorted(world._retabled)
    cells: list[tuple[str, str, Any, Any]] = []
    if everything:
        for kind in KINDS:
            for layer, table in getattr(tables, kind).items():
                cells += [(kind, layer, cell, value) for cell, value in table.items()]
    else:
        for net in nets:
            for kind, layer, cell in set(mirror.entries.get(net, ())) | set(
                tables.entries.get(net, ())
            ):
                value = getattr(tables, kind).get(layer, {}).get(cell)
                cells.append((kind, layer, cell, value))
    entries = [(net, list(tables.entries.get(net, ()))) for net in nets]
    pins = [(net, list(tables.pins.get(net, ()))) for net in nets]
    if everything:
        pins = [(net, list(p)) for net, p in tables.pins.items()]
        mirror.entries = {}
    for net, written in entries:
        mirror.entries[net] = written
    mirror.placements = dict(world.placements)
    mirror.wires = dict(world.wires)
    mirror.units = dict(world.units)
    world._retabled.clear()
    world._retable_all = False
    return {
        "full": full,
        "placements": placements,
        "order": order if changed_order else None,
        "wires": wires,
        "units": units,
        "tables_full": everything,
        "cells": cells,
        "entries": entries,
        "table_pins": pins,
        "share": share,
        "unit_seq": world._unit_seq,
    }


def native_route_all(
    router: Any, world: Any, cell_id: str, pending: list[str], grown: set[str]
) -> Refusal | None:
    """The twin's refusal for routing a placement's lanes; None lets Python route them."""
    grid = _native_grid(world)
    if grid is None:
        return None
    ordered = router.order(world, cell_id, pending, grown)
    if not ordered or any(world.netlist.nets[n].outside is not None for n in ordered):
        return None
    prepared = _prepared(world, router, grid)
    if prepared is None:
        return None
    mirror, fresh = prepared
    doc = {
        "sync": sync_doc(world, mirror, fresh),
        "nets": [{"net": net_id} for net_id in ordered],
        "history": _history(router),
    }
    text = rust_route_pass(grid, json.dumps(doc)[:-1] + _fixed(mirror, router))
    if text is None:
        return None
    answer = json.loads(text)
    if answer["kind"] != "refused":
        return None
    world._unit_seq = answer["unit_seq"]
    return refuse(answer["net"], f"not routed: {answer['detail']}")


def _prepared(world: Any, router: Any, grid: Any) -> tuple[Mirror, bool] | None:
    """The world's mirror, registered afresh when needed, and whether it was; None without costs."""
    mirror = _MIRRORS.get(world)
    if mirror is None:
        mirror = _MIRRORS[world] = Mirror()
    stamp = (id(grid), world.netlist, world.physics)
    fresh = (
        mirror.stamp is None or mirror.stamp[0] != stamp[0] or not grid.has_records()
    )
    fresh = fresh or mirror.stamp[1] is not stamp[1] or mirror.stamp[2] is not stamp[2]
    if fresh:
        for carrier in world.fabric.carriers:
            net = next(
                (n for n in world.netlist.nets.values() if n.carrier == carrier), None
            )
            if net is None:
                continue
            search = router.search(world, net, 1, frozenset({net.id}), True)
            register_walls(grid, search)
            mirror.keys[carrier] = (search.walls_key, search.unit_walls_key)
            mirror.costs = search.costs
        register_regions(grid, world)
        grid.register_records(json.dumps(statics(world, mirror, router)))
        mirror.stamp = stamp
    return (mirror, fresh) if mirror.costs is not None else None


def _native_grid(world: Any) -> Any:
    """The world's native grid when the twin can take its placements, else None."""
    router = world.router
    grid = getattr(world.kernel, "_grid", None)
    if (
        grid is None
        or not hasattr(grid, "attempt")
        or not getattr(router, "native_routing", False)
        or router.max_rips > 0
        or world.checker is not None
        or world._tables is None
    ):
        return None
    return grid


def _candidate(
    world: Any,
    mirror: Mirror,
    fresh: bool,
    cell: Any,
    fp: Any,
    x: int,
    y: int,
    rot: int,
) -> dict[str, Any]:
    """A candidate's document: the sync, the cell at its anchor and its pins' port choices."""
    return {
        "sync": sync_doc(world, mirror, fresh),
        "cell": cell.id,
        "x": x,
        "y": y,
        "rot": rot,
        "footprint": fp.id,
        "choices": [
            (pin.id, list(found))
            for pin in world.netlist.pins_of(cell.id)
            if (found := options_at(fp, pin, x, y, rot))
        ],
    }


def _fixed(mirror: Mirror, router: Any) -> str:
    """The routing settings that stand while the mirror does, encoded once as a JSON tail."""
    ripup, scale = router.costs.ripup, router.float_scale
    hit = mirror.fixed
    if hit is None or hit[0] is not mirror.stamp or hit[1:3] != (ripup, scale):
        fields = {
            "keys": [[c, w, u] for c, (w, u) in mirror.keys.items()],
            "costs": {**mirror.costs.model_dump(), "ripup": max(1, ripup)},
            "float_scale": router.float_scale,
        }
        mirror.fixed = (mirror.stamp, ripup, scale, ", " + json.dumps(fields)[1:])
    return mirror.fixed[3]


def _history(router: Any) -> list[tuple[str, int, int, int]]:
    """The router's history charges as ``(layer, x, y, count)`` rows."""
    return [(layer, xy[0], xy[1], n) for (layer, xy), n in router.history.items()]


def native_admits(
    world: Any, cell: Any, fp: Any, x: int, y: int, rot: int
) -> bool | None:
    """Whether the twin admits the cell at the anchor; None lets Python decide."""
    grid = _native_grid(world)
    if grid is None or not hasattr(grid, "admits"):
        return None
    prepared = _prepared(world, world.router, grid)
    if prepared is None:
        return None
    mirror, fresh = prepared
    doc = _candidate(world, mirror, fresh, cell, fp, x, y, rot)
    return rust_admits(grid, json.dumps(doc))


def native_attempt(
    world: Any, cell: Any, fp: Any, x: int, y: int, rot: int
) -> Refusal | None:
    """The twin's refusal for placing the cell at the anchor; None lets Python place it."""
    router = world.router
    grid = _native_grid(world)
    if grid is None:
        return None
    prepared = _prepared(world, router, grid)
    if prepared is None:
        return None
    mirror, fresh = prepared
    legal = world.physics.boundaries.legal(
        world, Placement(cell=cell.id, x=x, y=y, rot=rot)
    )
    doc = {
        **_candidate(world, mirror, fresh, cell, fp, x, y, rot),
        "legal": None if legal is None else [legal.stage, legal.subject, legal.detail],
        "history": _history(router),
    }
    text = rust_attempt(grid, json.dumps(doc)[:-1] + _fixed(mirror, router))
    if text is None:
        return None
    answer = json.loads(text)
    if answer["kind"] == "failed":
        failures = tuple(
            Refusal(stage=stage, subject=f"cell:{cell.id}", detail=detail)
            for stage, detail in answer["failures"]
        )
        return world.physics.diagnose(world, failures)
    if answer["kind"] != "refused":
        return None
    world._unit_seq = answer["unit_seq"]
    return Refusal(
        stage=answer["stage"], subject=answer["subject"], detail=answer["detail"]
    )


__all__ = [
    "Mirror",
    "native_admits",
    "native_attempt",
    "native_route_all",
    "occupant_of",
    "share_rows",
    "statics",
    "sync_doc",
]
