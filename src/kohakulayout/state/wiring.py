"""The wire side of the world: route a net, keep or take up its wire, and the units that go with it.

A mixin of ``World``; it reads the world's kernel, wires, units and router and writes
through the world's undo log like every other mutation.
"""

from collections.abc import Iterable
from typing import Any

from kohakulayout.errors import StateError
from kohakulayout.ir import Refusal, Wire
from kohakulayout.ir.geometry import XY
from kohakulayout.state.kernel import holder_kind


class WiringMixin:
    """Routing and wires: the world keeps the record, the router decides the paths."""

    netlist: Any
    kernel: Any
    router: Any
    wires: dict[str, Wire]
    units: dict[str, Any]

    def route(self, net_id: str, grow: bool = False) -> Refusal | None:
        """Route a net; with ``grow`` a routed net keeps its tree and reaches the pins it does not touch yet."""
        if net_id not in self.netlist.nets:
            raise StateError(f"no net {net_id!r}")
        if net_id in self.wires and not grow:
            return None
        pre_digest = self.digest() if self.checker is not None else ""
        if self.router is None:
            result: Refusal | None = Refusal(
                stage="route", subject=f"net:{net_id}", detail="no router is installed"
            )
        else:
            mark = self.mark()
            result = self.router.route(self, net_id)
            if result is not None:
                self.rollback_to(mark)
        if self.checker is not None:
            self.checker.on_route(self, net_id, result, pre_digest)
        return result

    def forget_routes(self) -> None:
        """Tell the router its negotiation history no longer describes this state."""
        self._tables = None
        forget = getattr(self.router, "forget", None)
        if forget is not None:
            forget()

    def set_wire(self, wire: Wire) -> None:
        """Record a routed wire and hold its cells; the router calls this after finding a path."""
        for segment in wire.segments:
            self._occupy((segment.layer,), tuple(segment.cells), f"wire:{wire.net}")
        self.wires[wire.net] = wire
        self.retable(wire.net)
        self._record(lambda: (self.wires.pop(wire.net, None), self.retable(wire.net)))

    def trim(self, net_id: str, cells: Iterable[XY]) -> bool:
        """Take up the segments of a net's wire that run through ``cells`` and every segment hanging from them (one leaving or joining a taken segment, at its own port cell only through a junction unit of the wire), the rest staying a routed wire the router grows again; False when nothing stays, so the caller takes the wire up whole."""
        wire = self.wires.get(net_id)
        if wire is None:
            return False
        hit = frozenset(cells)
        segments = list(wire.segments)
        gone = [seg for seg in segments if hit.intersection(seg.cells)]
        if not gone:
            return False
        ports = {
            xy
            for key, port_id in wire.ports.items()
            if (xy := self._attach_of(key, port_id)) is not None
        }
        for ref in self.netlist.nets[net_id].pins():
            if ref.cell in self.placements:
                ports.update(
                    a
                    for _, a, _ in self.port_choices(ref.cell).get(ref.pin, ())
                    if self.netlist.pin(ref) is None
                    or len(self.netlist.pin(ref).ports) <= 1
                )
        rule = self.physics.carriers.junction(self.netlist.nets[net_id].carrier)
        kinds = {fp.id for fp in (rule.split, rule.merge) if fp is not None}
        junctions = {
            (unit.x, unit.y)
            for unit_id in wire.units
            if (unit := self.units.get(unit_id)) is not None and unit.footprint in kinds
        }

        def hangs(end: XY, lost: set[XY]) -> bool:
            return end in lost and (end not in ports or end in junctions)

        lost: set[XY] = set()
        while True:
            lost = {c for seg in gone for c in seg.cells}
            more = [
                seg
                for seg in segments
                if seg not in gone
                and (hangs(seg.cells[0], lost) or hangs(seg.cells[-1], lost))
            ]
            if not more:
                break
            gone += more
        kept = [seg for seg in segments if seg not in gone]
        if not kept:
            return False
        staying = {c for seg in kept for c in seg.cells}
        freed = lost - staying
        cut = (
            {seg.cells[0] for seg in gone} | {seg.cells[-1] for seg in gone}
        ) & staying
        for layer in {seg.layer for seg in gone}:
            layer_cells = tuple(
                sorted(
                    c
                    for seg in gone
                    if seg.layer == layer
                    for c in seg.cells
                    if c in freed
                )
            )
            if layer_cells:
                self._free((layer,), layer_cells, f"wire:{net_id}")
        units = []
        for unit_id in wire.units:
            unit = self.units.get(unit_id)
            if unit is None:
                continue
            at = (unit.x, unit.y)
            if at in freed or (
                at in cut
                and not any(at in (seg.cells[0], seg.cells[-1]) for seg in kept)
            ):
                self.remove_unit(unit_id)
            else:
                units.append(unit_id)
        ports = {
            key: port_id
            for key, port_id in wire.ports.items()
            if self._attach_of(key, port_id) not in freed
        }
        trimmed = wire.model_copy(
            update={"segments": tuple(kept), "units": tuple(units), "ports": ports}
        )
        self.wires[net_id] = trimmed
        self.retable(net_id)
        self._record(
            lambda: (self.wires.__setitem__(net_id, wire), self.retable(net_id))
        )
        for layer in {seg.layer for seg in gone}:
            for xy in sorted(freed):
                for holder in self.kernel.holders_at(layer, xy):
                    kind, ref = holder_kind(holder)
                    if kind == "unit":
                        self._drop_shared_unit(ref, net_id)
        return True

    def _attach_of(self, key: str, port_id: str) -> XY | None:
        """The attach cell of a pin's recorded port, from its ``cell.pin`` key."""
        cell_id, pin_id = key.split(".", 1)
        for found, xy, _ in self.port_choices(cell_id).get(pin_id, ()):
            if found == port_id:
                return xy
        return None

    def unroute(self, net_id: str) -> None:
        """Free the wire, its units, and every other net's unit that only existed because of it."""
        wire = self.wires.get(net_id)
        if wire is None:
            return
        held = self.kernel.cells_of(f"wire:{net_id}")
        for layer, cells in held.items():
            self._free((layer,), tuple(sorted(cells)), f"wire:{net_id}")
        for unit_id in list(wire.units):
            self.remove_unit(unit_id)
        del self.wires[net_id]
        self.retable(net_id)
        self._record(
            lambda: (self.wires.__setitem__(net_id, wire), self.retable(net_id))
        )
        for layer, cells in held.items():
            for xy in sorted(cells):
                for holder in self.kernel.holders_at(layer, xy):
                    kind, ref = holder_kind(holder)
                    if kind == "unit":
                        self._drop_shared_unit(ref, net_id)

    def _drop_shared_unit(self, unit_id: str, gone: str) -> None:
        """A unit another net's wire lists, on a cell the ripped net held, was a crossing: it goes too."""
        unit = self.units.get(unit_id)
        if (
            unit is None
            or not unit.owner.startswith("net:")
            or unit.owner == f"net:{gone}"
        ):
            return
        other_id = unit.owner.removeprefix("net:")
        other = self.wires.get(other_id)
        if other is None or unit_id not in other.units:
            return
        self.remove_unit(unit_id)
        trimmed = other.model_copy(
            update={"units": tuple(u for u in other.units if u != unit_id)}
        )
        self.wires[other_id] = trimmed
        self._record(lambda: self.wires.__setitem__(other_id, other))
