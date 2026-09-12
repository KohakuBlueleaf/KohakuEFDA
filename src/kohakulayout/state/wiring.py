"""The wire side of the world: route a net, keep or take up its wire, and the units that go with it.

A mixin of ``World``; it reads the world's kernel, wires, units and router and writes
through the world's undo log like every other mutation.
"""

from collections.abc import Iterable
from typing import Any

from kohakulayout.errors import StateError
from kohakulayout.ir import Refusal, Wire
from kohakulayout.ir.geometry import XY
from kohakulayout.state.crossing import side_bit
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

    def runs_of(self, wire: Wire) -> dict[str, list[tuple[XY, int]]]:
        """Per layer, the sides the wire continues to on each cell, a used port behind included."""
        out: dict[str, dict[XY, int]] = {}
        for segment in wire.segments:
            table = out.setdefault(segment.layer, {})
            cells = segment.cells
            for i, xy in enumerate(cells):
                mask = table.get(xy, 0)
                if i > 0:
                    mask |= side_bit(xy, cells[i - 1])
                if i + 1 < len(cells):
                    mask |= side_bit(xy, cells[i + 1])
                table[xy] = mask
        net = self.netlist.nets[wire.net]
        table = out.get(self.carrier_layer(net.carrier))
        if table:
            for ref in net.pins():
                found = (
                    self.choice(ref.cell, ref.pin)
                    if ref.cell in self.placements
                    else None
                )
                if found is not None and found[1] in table:
                    table[found[1]] |= side_bit(found[1], found[2])
        return {layer: sorted(table.items()) for layer, table in out.items()}

    def set_wire(self, wire: Wire) -> None:
        """Record a routed wire, hold its cells and write its runs."""
        for segment in wire.segments:
            self._occupy((segment.layer,), tuple(segment.cells), f"wire:{wire.net}")
        self.wires[wire.net] = wire
        self.retable(wire.net)
        self._record(lambda: (self.wires.pop(wire.net, None), self.retable(wire.net)))
        self._write_runs(f"wire:{wire.net}", self.runs_of(wire), {})

    def trim(self, net_id: str, cells: Iterable[XY]) -> bool:
        """Take up the segments ``cells`` cut and every segment hanging from them.

        A segment hangs from a taken one when an end of it lies on that segment's own cells; the
        rest stays a routed wire. False when nothing stays.
        """
        wire = self.wires.get(net_id)
        if wire is None:
            return False
        hit = frozenset(cells)
        segments = list(wire.segments)
        gone = [seg for seg in segments if hit.intersection(seg.cells)]
        if not gone:
            return False
        before = self.runs_of(wire)
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

        def hangs_at(i: int, end: XY) -> bool:
            """Whether a segment's end lies on an earlier lane, or on any other off a port cell."""
            if any(end in other.cells for other in segments[:i]):
                return True
            return end not in ports and any(
                end in other.cells for j, other in enumerate(segments) if j != i
            )

        leaves = [hangs_at(i, seg.cells[0]) for i, seg in enumerate(segments)]
        joins = [hangs_at(i, seg.cells[-1]) for i, seg in enumerate(segments)]

        def own(i: int) -> set[XY]:
            """A segment's own cells: the end it leaves from or joins at belongs to the earlier lane there."""
            cells = set(segments[i].cells)
            if leaves[i]:
                cells.discard(segments[i].cells[0])
            if joins[i]:
                cells.discard(segments[i].cells[-1])
            return cells

        while True:
            lost = set().union(
                *(own(i) for i, seg in enumerate(segments) if seg in gone)
            )
            more = [
                seg
                for i, seg in enumerate(segments)
                if seg not in gone
                and (
                    (leaves[i] and seg.cells[0] in lost)
                    or (joins[i] and seg.cells[-1] in lost)
                )
            ]
            if not more:
                break
            gone += more
        lost = {c for seg in gone for c in seg.cells}
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
        self._write_runs(f"wire:{net_id}", self.runs_of(trimmed), before)
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
        self._write_runs(f"wire:{net_id}", {}, self.runs_of(wire))
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
