"""L3, the Netlist: what must exist and how it must connect, with modules and macros."""

from typing import Any, ClassVar

from kohakulayout._rust_bridge import rust_flatten
from kohakulayout.ir.base import Attrs, Level, check_attrs, jsonable
from kohakulayout.ir.netlist.hier import Macro, Module, ModulePort, derive_footprint
from kohakulayout.ir.netlist.model import (
    DIRECTIONS,
    Cell,
    Constraint,
    Direction,
    Footprint,
    Group,
    Net,
    Pin,
    PinRef,
    Port,
)
from kohakulayout.ir.netlist.order import flow_order as _flow_order

__all__ = [
    "DIRECTIONS",
    "Cell",
    "Constraint",
    "Direction",
    "Footprint",
    "Group",
    "Macro",
    "Module",
    "ModulePort",
    "Net",
    "Netlist",
    "Pin",
    "PinRef",
    "Port",
    "derive_footprint",
]


class Netlist(Level):
    level: ClassVar[str] = "netlist"
    pack: str = ""
    library: dict[str, Footprint] = {}
    cells: dict[str, Cell] = {}
    nets: dict[str, Net] = {}
    groups: dict[str, Group] = {}
    modules: dict[str, Module] = {}
    macros: dict[str, Macro] = {}
    attrs: Attrs = {}

    # ------------------------------------------------------------ lookups
    def footprint_for(self, cell_id: str) -> Footprint | None:
        cell = self.cells.get(cell_id)
        if cell is None:
            return None
        if cell.footprint is not None:
            return self.library.get(cell.footprint)
        if cell.macro is not None:
            macro = self.macros.get(cell.macro)
            return macro.footprint if macro is not None else None
        return None

    def pins_of(self, cell_id: str) -> tuple[Pin, ...]:
        """Explicit pins, else one pin per port of the footprint or module."""
        cell = self.cells.get(cell_id)
        if cell is None:
            return ()
        if cell.pins:
            return cell.pins
        ports: tuple[Port, ...] | tuple[ModulePort, ...] = ()
        fp = self.footprint_for(cell_id)
        if fp is not None:
            ports = fp.ports
        elif cell.module is not None and cell.module in self.modules:
            ports = self.modules[cell.module].ports
        elif cell.macro is not None and cell.macro in self.macros:
            module = self.modules.get(self.macros[cell.macro].module)
            ports = module.ports if module is not None else ()
        return tuple(
            Pin(id=p.id, direction=p.direction, carrier=p.carrier, ports=(p.id,))
            for p in ports
        )

    def pin(self, ref: PinRef) -> Pin | None:
        for pin in self.pins_of(ref.cell):
            if pin.id == ref.pin:
                return pin
        return None

    @property
    def is_flat(self) -> bool:
        return not any(c.is_instance for c in self.cells.values())

    def with_library(self, parent: "Netlist") -> "Netlist":
        """This netlist seen with a parent's library and definitions behind its own."""
        return self.model_copy(
            update={
                "library": {**parent.library, **self.library},
                "modules": {**parent.modules, **self.modules},
                "macros": {**parent.macros, **self.macros},
            }
        )

    # ------------------------------------------------------------ checks
    def check(self) -> list[str]:
        problems = self._check_scope("netlist", self)
        problems += check_attrs(self.attrs, "netlist")
        return problems

    def _check_scope(self, where: str, own: "Netlist") -> list[str]:
        """Check ``own``'s definitions, resolving names through ``self`` (own plus its parents)."""
        problems: list[str] = []
        for key, fp in own.library.items():
            if key != fp.id:
                problems.append(f"{where}: library key {key!r} names {fp.id!r}")
            problems += fp.check()
        for key, cell in own.cells.items():
            if key != cell.id:
                problems.append(f"{where}: cell key {key!r} names {cell.id!r}")
            problems += self._check_cell(cell, where)
        used: dict[str, str] = {}
        for key, net in own.nets.items():
            if key != net.id:
                problems.append(f"{where}: net key {key!r} names {net.id!r}")
            problems += self._check_net(net, used, where)
        for key, group in own.groups.items():
            if key != group.id:
                problems.append(f"{where}: group key {key!r} names {group.id!r}")
            for member in group.members:
                cell = self.cells.get(member)
                if cell is None:
                    problems.append(
                        f"group {group.id}: member {member!r} does not exist"
                    )
                elif cell.group != group.id:
                    problems.append(
                        f"group {group.id}: member {member!r} does not name this group"
                    )
            problems += check_attrs(group.attrs, f"group {group.id}")
        problems += self._check_definitions(where, own)
        return problems

    def _check_cell(self, cell: Cell, where: str) -> list[str]:
        problems = check_attrs(cell.attrs, f"cell {cell.id}")
        refs = sum(x is not None for x in (cell.footprint, cell.module, cell.macro))
        if refs != 1:
            problems.append(
                f"cell {cell.id}: names {refs} of footprint, module and macro; exactly one is required"
            )
            return problems
        if cell.footprint is not None and cell.footprint not in self.library:
            problems.append(
                f"cell {cell.id}: footprint {cell.footprint!r} is not in the library"
            )
        if cell.module is not None and cell.module not in self.modules:
            problems.append(f"cell {cell.id}: module {cell.module!r} is not defined")
        if cell.macro is not None and cell.macro not in self.macros:
            problems.append(f"cell {cell.id}: macro {cell.macro!r} is not defined")
        if cell.group is not None and cell.group not in self.groups:
            problems.append(f"cell {cell.id}: group {cell.group!r} does not exist")
        problems += check_attrs(cell.constraint.attrs, f"cell {cell.id} constraint")
        fp = self.footprint_for(cell.id)
        module = self.modules.get(cell.module) if cell.module else None
        for pin in cell.pins:
            if pin.direction not in DIRECTIONS:
                problems.append(
                    f"cell {cell.id}: pin {pin.id} direction {pin.direction!r}"
                )
            if not pin.ports:
                problems.append(f"cell {cell.id}: pin {pin.id} may use no port")
            for port_id in pin.ports:
                port = fp.port(port_id) if fp is not None else None
                mport = (
                    next((p for p in module.ports if p.id == port_id), None)
                    if module
                    else None
                )
                target = port or mport
                if target is None:
                    problems.append(
                        f"cell {cell.id}: pin {pin.id} names a missing port {port_id!r}"
                    )
                elif target.carrier != pin.carrier or target.direction != pin.direction:
                    problems.append(
                        f"cell {cell.id}: pin {pin.id} and port {port_id} disagree on carrier or direction"
                    )
        return problems

    def _check_net(self, net: Net, used: dict[str, str], where: str) -> list[str]:
        problems = check_attrs(net.attrs, f"net {net.id}")
        if net.rate < 0:
            problems.append(f"net {net.id}: negative rate")
        if not net.sources and net.outside is None:
            problems.append(f"net {net.id}: no source and no outside side")
        for role, refs, wanted in (
            ("source", net.sources, ("out", "inout")),
            ("sink", net.sinks, ("in", "inout")),
        ):
            for ref in refs:
                pin = self.pin(ref)
                if ref.cell not in self.cells:
                    problems.append(f"net {net.id}: {role} {ref} names a missing cell")
                elif pin is None:
                    problems.append(f"net {net.id}: {role} {ref} names a missing pin")
                else:
                    if pin.direction not in wanted:
                        problems.append(
                            f"net {net.id}: {role} {ref} is an {pin.direction} pin"
                        )
                    if pin.carrier != net.carrier:
                        problems.append(
                            f"net {net.id}: {role} {ref} carries {pin.carrier!r}, not {net.carrier!r}"
                        )
                key = str(ref)
                if key in used and used[key] != net.id:
                    problems.append(
                        f"net {net.id}: pin {ref} is already on net {used[key]}"
                    )
                used[key] = net.id
        return problems

    def _check_definitions(self, where: str, own: "Netlist") -> list[str]:
        problems: list[str] = []
        names = set(own.library) | set(own.modules) | set(own.macros)
        if len(names) != len(own.library) + len(own.modules) + len(own.macros):
            problems.append(f"{where}: a footprint, module and macro share an id")
        for key, module in own.modules.items():
            if key != module.id:
                problems.append(f"{where}: module key {key!r} names {module.id!r}")
            body = module.body.with_library(self)
            problems += body._check_scope(f"module {module.id}", module.body)
            for mport in module.ports:
                if body.pin(mport.inner) is None:
                    problems.append(
                        f"module {module.id}: port {mport.id} binds to a missing pin {mport.inner}"
                    )
            problems += self._check_no_recursion(module.id, module, set())
        for key, macro in own.macros.items():
            if key != macro.id:
                problems.append(f"{where}: macro key {key!r} names {macro.id!r}")
            problems += self._check_macro(macro)
        return problems

    def _check_no_recursion(
        self, root: str, module: Module, seen: set[str]
    ) -> list[str]:
        for cell in module.body.cells.values():
            target = cell.module or (
                self.macros[cell.macro].module if cell.macro in self.macros else None
            )
            if target == root:
                return [f"module {root}: instantiates itself"]
            if target in self.modules and target not in seen:
                found = self._check_no_recursion(
                    root, self.modules[target], seen | {target}
                )
                if found:
                    return found
        return []

    def _check_macro(self, macro: Macro) -> list[str]:
        module = self.modules.get(macro.module)
        if module is None:
            return [f"macro {macro.id}: module {macro.module!r} is not defined"]
        body = module.body.with_library(self).flatten()
        leaves = set(body.cells)
        placed = set(macro.layout.placements)
        problems: list[str] = []
        if placed != leaves:
            problems.append(
                f"macro {macro.id}: the fragment places {sorted(placed)}, the module has {sorted(leaves)}"
            )
            return problems
        footprints = {k: body.footprint_for(k) for k in leaves}
        pins = {k: {p.id: p.ports for p in body.pins_of(k)} for k in leaves}
        derived, errors = derive_footprint(
            macro, module, {k: v for k, v in footprints.items() if v}, pins
        )
        problems += errors
        if (
            derived is not None
            and macro.footprint is not None
            and derived != macro.footprint
        ):
            problems.append(
                f"macro {macro.id}: the stored footprint disagrees with the derived one"
            )
        problems += macro.layout.check()
        problems += [
            f"macro {macro.id}: {p}" for p in macro.layout.check_against(body, None)
        ]
        return problems

    # ------------------------------------------------------------ hierarchy
    def flatten(self) -> "Netlist":
        """Every instance expanded, ids joined with ``/``, port nets merged, definitions dropped; entries in id order."""
        if self.is_flat:
            return self.model_copy(
                update={
                    "library": dict(sorted(self.library.items())),
                    "cells": dict(sorted(self.cells.items())),
                    "nets": dict(sorted(self.nets.items())),
                    "groups": dict(sorted(self.groups.items())),
                    "modules": {},
                    "macros": {},
                }
            )
        native = rust_flatten(self.to_json())
        if native is not None:
            return Netlist.from_json(native)
        cells = dict(self.cells)
        nets = dict(self.nets)
        groups = dict(self.groups)
        for key, cell in sorted(self.cells.items()):
            if not cell.is_instance:
                continue
            module_id = cell.module or self.macros[cell.macro].module
            module = self.modules[module_id]
            body = module.body.with_library(self).flatten()
            prefix = key + "/"
            del cells[key]
            for leaf_key, leaf in body.cells.items():
                cells[prefix + leaf_key] = leaf.model_copy(
                    update={
                        "id": prefix + leaf_key,
                        "group": prefix + leaf.group if leaf.group else None,
                    }
                )
            for group_key, group in body.groups.items():
                groups[prefix + group_key] = group.model_copy(
                    update={
                        "id": prefix + group_key,
                        "members": tuple(prefix + m for m in group.members),
                    }
                )
            inner_nets = {
                prefix
                + net_key: net.model_copy(
                    update={
                        "id": prefix + net_key,
                        "sources": tuple(
                            PinRef(cell=prefix + r.cell, pin=r.pin) for r in net.sources
                        ),
                        "sinks": tuple(
                            PinRef(cell=prefix + r.cell, pin=r.pin) for r in net.sinks
                        ),
                    }
                )
                for net_key, net in body.nets.items()
            }
            portmap = {
                p.id: PinRef(cell=prefix + p.inner.cell, pin=p.inner.pin)
                for p in module.ports
            }
            for net_key, net in list(nets.items()):
                sources = tuple(
                    portmap.get(r.pin, r) if r.cell == key else r for r in net.sources
                )
                sinks = tuple(
                    portmap.get(r.pin, r) if r.cell == key else r for r in net.sinks
                )
                if sources == net.sources and sinks == net.sinks:
                    continue
                merged = net.model_copy(update={"sources": sources, "sinks": sinks})
                for inner_key, inner in list(inner_nets.items()):
                    shared = set(map(str, inner.pins())) & set(map(str, merged.pins()))
                    if shared:
                        merged = merged.model_copy(
                            update={
                                "sources": _union(merged.sources, inner.sources),
                                "sinks": _union(merged.sinks, inner.sinks),
                            }
                        )
                        del inner_nets[inner_key]
                nets[net_key] = merged
            nets.update(inner_nets)
        return Netlist(
            schema_version=self.schema_version,
            pack=self.pack,
            library=self.library,
            cells=cells,
            nets=nets,
            groups=groups,
            attrs=self.attrs,
        )

    def canonical(self) -> dict[str, Any]:
        flat = self.flatten()
        return {"level": self.level, **jsonable(flat.model_dump(mode="python"))}

    # ------------------------------------------------------------ structure
    def flow_order(self) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
        flat = self.flatten()
        edges = [
            (src.cell, sink.cell)
            for net in flat.nets.values()
            for src in net.sources
            for sink in net.sinks
        ]
        return _flow_order(flat.cells, edges)

    def fanout(self, cell_id: str) -> int:
        return sum(
            len(n.sinks)
            for n in self.nets.values()
            if any(r.cell == cell_id for r in n.sources)
        )

    def fanin(self, cell_id: str) -> int:
        return sum(1 for n in self.nets.values() for r in n.sinks if r.cell == cell_id)


def _union(first: tuple[PinRef, ...], second: tuple[PinRef, ...]) -> tuple[PinRef, ...]:
    seen = {str(r) for r in first}
    return first + tuple(r for r in second if str(r) not in seen)


Module.model_rebuild(_types_namespace={"Netlist": Netlist})
Macro.model_rebuild(_types_namespace={"Netlist": Netlist})
Netlist.model_rebuild()
