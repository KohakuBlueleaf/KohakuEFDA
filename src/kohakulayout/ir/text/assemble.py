"""Statement records to levels: the fabric, the netlist with its scopes, the layout, the assessment."""

import json
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from kohakulayout.errors import TextError
from kohakulayout.ir.assessment import Assessment, Finding
from kohakulayout.ir.fabric import Carrier, Fabric, Rect, Region
from kohakulayout.ir.layout import Layout, Placement, Reservation, Segment, Unit, Wire
from kohakulayout.ir.netlist import (
    Cell,
    Constraint,
    Footprint,
    Group,
    Macro,
    Module,
    ModulePort,
    Net,
    Netlist,
    Pin,
    PinRef,
    Port,
    derive_footprint,
)
from kohakulayout.ir.problem import Problem
from kohakulayout.ir.text.moves import cells_from_moves, parse_move

CELL_OPTS = {"kind", "at", "group", "needs", "label"}


@dataclass
class Levels:
    """Every level one text may hold. ``problem`` exists when a fabric and a netlist do."""

    version: int = 1
    physics: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    fabric: Fabric | None = None
    netlist: Netlist | None = None
    layout: Layout | None = None
    assessment: Assessment | None = None

    @property
    def problem(self) -> Problem | None:
        if self.fabric is None or self.netlist is None:
            return None
        return Problem(
            physics=self.physics,
            fabric=self.fabric,
            netlist=self.netlist,
            params=self.params,
        )

    def pick(self, cls: type) -> Any:
        for candidate in (self.problem, self.netlist, self.layout, self.assessment):
            if isinstance(candidate, cls):
                return candidate
        return None


def levels_from_json(text: str) -> Levels:
    """The levels document the native twin returns, as :class:`Levels`."""
    raw = json.loads(text)
    out = Levels(
        version=int(raw.get("version", 1)),
        physics=str(raw.get("physics", "")),
        params=dict(raw.get("params", {})),
    )
    if raw.get("fabric") is not None:
        out.fabric = Fabric.model_validate(raw["fabric"])
    if raw.get("netlist") is not None:
        out.netlist = Netlist.from_json(json.dumps(raw["netlist"]))
    if raw.get("layout") is not None:
        out.layout = Layout.from_json(json.dumps(raw["layout"]))
    if raw.get("assessment") is not None:
        out.assessment = Assessment.from_json(json.dumps(raw["assessment"]))
    return out


def _as_tuple(value: Any) -> tuple:
    if value is None:
        return ()
    if isinstance(value, list | tuple):
        return tuple(value)
    return (value,)


def _rate(value: Any) -> Fraction:
    return Fraction(0) if value is None else Fraction(value)


def _fabric(stmts: list[dict]) -> Fabric | None:
    head = next((s for s in stmts if s["stmt"] == "fabric"), None)
    if head is None:
        return None
    width, height = head["size"]
    layers = tuple(str(v) for v in _as_tuple(head["opts"].get("layers", "ground")))
    entries = tuple(str(v) for v in _as_tuple(head["opts"].get("entries")))
    carriers = {
        s["id"]: Carrier(
            id=s["id"], layer=s["layer"], capacity=s["capacity"], attrs=s["attrs"]
        )
        for s in stmts
        if s["stmt"] == "carrier"
    }
    every = frozenset((x, y) for y in range(height) for x in range(width))
    regions: dict[str, Region] = {}
    pending = [s for s in stmts if s["stmt"] == "region"]
    for s in [p for p in pending if p["expr"][0] != "not"]:
        cells = (
            every
            if s["expr"][0] == "all"
            else frozenset().union(
                *[Rect(x=r[1], y=r[2], w=r[3], h=r[4]).cells() for r in s["expr"][1]]
            )
        )
        regions[s["id"]] = Region.of(s["id"], cells, s["attrs"])
    for s in [p for p in pending if p["expr"][0] == "not"]:
        other = regions.get(s["expr"][1])
        if other is None:
            raise TextError(
                f"region {s['id']}: 'not {s['expr'][1]}' names an undefined region"
            )
        regions[s["id"]] = Region.of(s["id"], every - other.cells(), s["attrs"])
    if "build" not in regions:
        regions["build"] = Region.of("build", every)
    return Fabric(
        width=width,
        height=height,
        layers=layers,
        carriers=carriers,
        regions=regions,
        entries=entries,
        attrs=head["attrs"],
    )


def _constraint(opts: dict[str, Any], pack: str) -> Constraint:
    kind = str(opts.get("at", "free"))
    attrs: dict[str, dict[str, Any]] = {}
    for key, value in opts.items():
        if key in CELL_OPTS:
            continue
        if key.startswith("at."):
            _, namespace, name = key.split(".", 2)
            attrs.setdefault(namespace, {})[name] = value
        else:
            attrs.setdefault(pack or "pack", {})[key] = value
    return Constraint(kind=kind, attrs=attrs)


def _scope(items: list[dict], pack: str, parent: Netlist | None) -> Netlist:
    """A netlist from the statements of one scope, resolving refs after every definition is seen."""
    library = {
        s["id"]: Footprint(
            id=s["id"],
            width=s["size"][0],
            height=s["size"][1],
            layer=str(s["opts"].get("layer", "ground")),
            occludes=tuple(str(v) for v in _as_tuple(s["opts"].get("occludes"))),
            rotations=tuple(
                int(v) for v in _as_tuple(s["opts"].get("rot", [0, 90, 180, 270]))
            ),
            ports=tuple(
                Port(
                    id=p[1],
                    direction=p[2],
                    carrier=p[3],
                    side=p[4],
                    offset=p[5],
                    attrs=p[6],
                )
                for p in s["ports"]
            ),
            attrs=s["attrs"],
        )
        for s in items
        if s["stmt"] == "lib"
    }
    seen_library = {**(parent.library if parent else {}), **library}
    modules: dict[str, Module] = {}
    for s in items:
        if s["stmt"] != "module":
            continue
        ports = tuple(
            ModulePort(
                id=p["id"],
                direction=p["direction"],
                carrier=p["carrier"],
                inner=PinRef(cell=p["cell"], pin=p["pin"]),
            )
            for p in s["items"]
            if p["stmt"] == "module_port"
        )
        body_items = [p for p in s["items"] if p["stmt"] != "module_port"]
        scope_parent = Netlist(
            pack=pack,
            library=seen_library,
            modules={**(parent.modules if parent else {}), **modules},
        )
        modules[s["id"]] = Module(
            id=s["id"], ports=ports, body=_scope(body_items, pack, scope_parent)
        )
    seen_modules = {**(parent.modules if parent else {}), **modules}
    macros: dict[str, Macro] = {}
    for s in items:
        if s["stmt"] != "macro":
            continue
        fragment = _layout(s["items"], Levels(fabric=None, netlist=None), relative=True)
        macros[s["id"]] = Macro(id=s["id"], module=s["module"], layout=fragment)
    seen_macros = {**(parent.macros if parent else {}), **macros}
    cells: dict[str, Cell] = {}
    for s in items:
        if s["stmt"] != "cell":
            continue
        ref = s["ref"]
        target = {"footprint": None, "module": None, "macro": None}
        if ref in seen_library:
            target["footprint"] = ref
        elif ref in seen_modules:
            target["module"] = ref
        elif ref in seen_macros:
            target["macro"] = ref
        else:
            raise TextError(
                f"cell {s['id']}: {ref!r} is not a footprint, module or macro"
            )
        opts = s["opts"]
        cells[s["id"]] = Cell(
            id=s["id"],
            kind=str(opts.get("kind", ref)),
            label=str(opts.get("label", "")),
            attrs=s["attrs"],
            pins=(),
            constraint=_constraint(opts, pack),
            group=str(opts["group"]) if "group" in opts else None,
            needs=tuple(str(v) for v in _as_tuple(opts.get("needs"))),
            **target,
        )
    for s in items:
        if s["stmt"] != "pin":
            continue
        cell = cells.get(s["cell"])
        if cell is None:
            raise TextError(f"pin {s['cell']}.{s['pin']}: no such cell in this scope")
        ports = tuple(str(p) for p in str(s["opts"].get("ports", s["pin"])).split("|"))
        pin = Pin(
            id=s["pin"], direction=s["direction"], carrier=s["carrier"], ports=ports
        )
        cells[s["cell"]] = cell.model_copy(update={"pins": cell.pins + (pin,)})
    groups: dict[str, Group] = {}
    for s in items:
        if s["stmt"] != "group":
            continue
        groups[s["id"]] = Group(
            id=s["id"],
            kind=str(s["opts"].get("kind", "")),
            attrs=s["attrs"],
            members=tuple(s["members"]),
        )
        for member in s["members"]:
            if member in cells:
                cells[member] = cells[member].model_copy(update={"group": s["id"]})
    nets: dict[str, Net] = {}
    for s in items:
        if s["stmt"] != "net":
            continue
        opts = s["opts"]
        nets[s["id"]] = Net(
            id=s["id"],
            kind=str(opts.get("kind", "")),
            label=str(opts.get("label", "")),
            attrs=s["attrs"],
            carrier=s["carrier"],
            rate=_rate(s["rate"]),
            sources=tuple(
                PinRef(cell=r.split(".", 1)[0], pin=r.split(".", 1)[1])
                for r in s["sources"]
            ),
            sinks=tuple(
                PinRef(cell=r.split(".", 1)[0], pin=r.split(".", 1)[1])
                for r in s["sinks"]
            ),
            outside=str(opts["outside"]) if "outside" in opts else None,
        )
    attrs: dict[str, dict[str, Any]] = {}
    for s in items:
        if s["stmt"] == "attrs":
            for namespace, values in s["attrs"].items():
                attrs.setdefault(namespace, {}).update(values)
    netlist = Netlist(
        pack=pack if parent is None else "",
        library=library,
        cells=cells,
        nets=nets,
        groups=groups,
        modules=modules,
        macros=macros,
        attrs=attrs,
    )
    return _derive_macros(netlist, parent)


def _derive_macros(netlist: Netlist, parent: Netlist | None) -> Netlist:
    if not netlist.macros:
        return netlist
    scope = netlist.with_library(parent) if parent else netlist
    macros: dict[str, Macro] = {}
    for key, macro in netlist.macros.items():
        module = scope.modules.get(macro.module)
        if module is None:
            raise TextError(f"macro {key}: module {macro.module!r} is not defined")
        body = module.body.with_library(scope).flatten()
        footprints = {
            k: fp for k in body.cells if (fp := body.footprint_for(k)) is not None
        }
        pins = {k: {p.id: p.ports for p in body.pins_of(k)} for k in body.cells}
        derived, problems = derive_footprint(macro, module, footprints, pins)
        if problems:
            raise TextError("; ".join(problems))
        macros[key] = macro.model_copy(update={"footprint": derived})
    return netlist.model_copy(update={"macros": macros})


def _endpoint(
    item: Any, netlist: Netlist | None, layout: Layout, net: Net | None
) -> tuple:
    if isinstance(item, tuple) and item[0] == "cell":
        return item[1]
    cell, pin = str(item).split(".", 1)
    if netlist is None:
        raise TextError(
            f"wire endpoint {item}: a pin reference needs the netlist in context"
        )
    attach = layout.attach(netlist, PinRef(cell=cell, pin=pin))
    if attach is None:
        raise TextError(
            f"wire endpoint {item}: the cell is not placed or the pin is unknown"
        )
    return attach


def _layout(stmts: list[dict], context: Levels, relative: bool = False) -> Layout:
    netlist = context.netlist.flatten() if context.netlist is not None else None
    fabric = context.fabric
    head = next((s for s in stmts if s["stmt"] == "layout"), None)
    placements = {
        s["cell"]: Placement(cell=s["cell"], x=s["xy"][0], y=s["xy"][1], rot=s["rot"])
        for s in stmts
        if s["stmt"] == "place"
    }
    instances = {
        s["cell"]: Placement(cell=s["cell"], x=s["xy"][0], y=s["xy"][1], rot=s["rot"])
        for s in stmts
        if s["stmt"] == "instance"
    }
    partial = Layout(placements=placements, instances=instances)
    wires: dict[str, Wire] = {}
    for s in stmts:
        if s["stmt"] != "wire":
            continue
        net = netlist.nets.get(s["net"]) if netlist is not None else None
        carrier = str(s["opts"].get("carrier", net.carrier if net else ""))
        layer = str(
            s["opts"].get(
                "layer",
                (
                    fabric.carriers[carrier].layer
                    if fabric and carrier in fabric.carriers
                    else ""
                ),
            )
        )
        if not carrier or not layer:
            raise TextError(
                f"wire {s['net']}: carrier and layer are unknown; give carrier= and layer= or the problem"
            )
        segments = []
        for seg in s["segments"]:
            end = _endpoint(seg["end"], netlist, partial, net)
            if "cells" in seg:
                cells = tuple(seg["cells"])
                if cells[-1] != end:
                    cells = cells + (end,) if end != cells[-1] else cells
            else:
                start = _endpoint(seg["start"], netlist, partial, net)
                moves = [
                    parse_move(str(m)) if not isinstance(m, tuple) else m
                    for m in seg["moves"]
                ]
                cells = cells_from_moves(start, moves)
                if cells[-1] != end:
                    raise TextError(
                        f"wire {s['net']}: the path ends at {cells[-1]}, not at {end}"
                    )
            segments.append(Segment(carrier=carrier, layer=layer, cells=cells))
        wires[s["net"]] = Wire(
            net=s["net"],
            segments=tuple(segments),
            units=tuple(str(u) for u in _as_tuple(s["opts"].get("units"))),
        )
    units = {
        s["id"]: Unit(
            id=s["id"],
            kind=str(s["opts"].get("kind", s["footprint"])),
            footprint=s["footprint"],
            x=s["xy"][0],
            y=s["xy"][1],
            rot=s["rot"],
            owner=str(s["opts"].get("owner", "")),
            attrs=s["attrs"],
        )
        for s in stmts
        if s["stmt"] == "unit"
    }
    reservations = tuple(
        Reservation(
            tag=s["tag"],
            layer=s["layer"],
            carrier=str(s["opts"]["carrier"]) if "carrier" in s["opts"] else None,
            cells=tuple(
                sorted(
                    frozenset().union(
                        *[
                            Rect(x=r[1], y=r[2], w=r[3], h=r[4]).cells()
                            for r in s["rects"]
                        ]
                    )
                )
            ),
        )
        for s in stmts
        if s["stmt"] == "reserve"
    )
    return Layout(
        problem=head["digest"] if head else "",
        placements=placements,
        instances=instances,
        wires=wires,
        units=units,
        reservations=reservations,
        attrs=head["attrs"] if head else {},
    )


def _assessment(stmts: list[dict]) -> Assessment | None:
    head = next((s for s in stmts if s["stmt"] == "assessment"), None)
    metrics = {s["name"]: s["value"] for s in stmts if s["stmt"] == "metric"}
    findings = tuple(
        Finding(
            rule=s["rule"],
            severity=s["severity"],
            subject=s["subject"],
            message=s["message"],
            attrs=s["attrs"],
        )
        for s in stmts
        if s["stmt"] == "finding"
    )
    if head is None and not metrics and not findings:
        return None
    complete = next((s["value"] for s in stmts if s["stmt"] == "complete"), False)
    valid = next((s["value"] for s in stmts if s["stmt"] == "valid"), False)
    return Assessment(
        layout=head["digest"] if head else "",
        metrics=metrics,
        findings=findings,
        complete=complete,
        valid=valid,
    )


NETLIST_STMTS = {"lib", "cell", "pin", "net", "group", "module", "macro", "attrs"}
LAYOUT_STMTS = {"layout", "place", "instance", "wire", "unit", "reserve"}
ASSESS_STMTS = {"assessment", "metric", "finding", "complete", "valid"}


def assemble(stmts: list[dict], context: Levels | None = None) -> Levels:
    out = Levels()
    head = next((s for s in stmts if s["stmt"] == "header"), None)
    out.version = head["version"] if head else 1
    out.physics = next(
        (s["id"] for s in stmts if s["stmt"] == "physics"),
        context.physics if context else "",
    )
    out.params = {s["key"]: s["value"] for s in stmts if s["stmt"] == "param"}
    out.fabric = _fabric(stmts) or (context.fabric if context else None)
    pack = out.physics.split("@")[0] if out.physics else ""
    netlist_items = [s for s in stmts if s["stmt"] in NETLIST_STMTS]
    if netlist_items:
        out.netlist = _scope(netlist_items, pack, None)
    elif context is not None:
        out.netlist = context.netlist
    layout_items = [s for s in stmts if s["stmt"] in LAYOUT_STMTS]
    if layout_items:
        out.layout = _layout(layout_items, out)
    out.assessment = _assessment([s for s in stmts if s["stmt"] in ASSESS_STMTS])
    return out
