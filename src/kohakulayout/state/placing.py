"""Placing leaf cells and instances: the failure chain, the settled placement, its wiring, the instance placed as one, and withdrawal."""

from typing import Any

from kohakulayout.errors import StateError
from kohakulayout.ir import Footprint, Layout, Placement, Refusal
from kohakulayout.ir.geometry import ROTATIONS, footprint_cells
from kohakulayout.physics.protocol import Anchor
from kohakulayout.state.chain import cover, inspect, recover
from kohakulayout.state.router.native_route import native_attempt


class PlacingMixin:
    """The world's placement operations; mixed into ``World``."""

    def place(self, cell_id: str, x: int, y: int, rot: int = 0) -> Refusal | None:
        """Place a leaf cell, route the nets it makes routable and grow the routed ones to its pins, then cover its needs around the wires; refuse and roll back otherwise."""
        cell = self.netlist.cells.get(cell_id)
        if cell is None:
            raise StateError(f"{cell_id!r} is not a leaf cell of the problem")
        if cell_id in self.placements:
            raise StateError(f"{cell_id!r} is already placed")
        fp = self.footprint_of(cell_id)
        if fp is None:
            raise StateError(f"{cell_id!r} has no footprint")
        if rot not in ROTATIONS:
            raise StateError(f"rotation {rot!r} is not one of {ROTATIONS}")
        if self.checker is None and self.native_attempts and not self.report_frontier:
            native = native_attempt(self, cell, fp, x, y, rot)
            if native is not None:
                return native
        pre_digest = self.digest() if self.checker is not None else ""
        mark = self.mark()
        result = self._place(cell, fp, x, y, rot)
        if result is not None:
            self.rollback_to(mark)
        if self.checker is not None:
            self.checker.on_place(
                self, cell_id, Anchor(x=x, y=y, rot=rot), result, pre_digest
            )
        return result

    def place_batch(self, anchors: dict[str, Anchor]) -> Refusal | None:
        """Settle every leaf before routing any, atomically; checked worlds use checked singles."""
        for cell_id, anchor in anchors.items():
            if cell_id not in self.netlist.cells or self.footprint_of(cell_id) is None:
                raise StateError(f"{cell_id!r} is not a placeable leaf")
            if cell_id in self.placements:
                raise StateError(f"{cell_id!r} is already placed")
            if anchor.rot not in ROTATIONS:
                raise StateError(f"invalid rotation {anchor.rot!r}")
        mark = self.mark()
        accepted = False
        try:
            settled: list[tuple[Any, ...]] = []
            for cell_id, anchor in anchors.items():
                if self.checker is not None:
                    found = self.place(cell_id, anchor.x, anchor.y, anchor.rot)
                else:
                    found = self._settle(
                        self.netlist.cells[cell_id],
                        self.footprint_of(cell_id),
                        anchor.x,
                        anchor.y,
                        anchor.rot,
                    )
                if isinstance(found, Refusal):
                    return found
                if found is not None:
                    settled.append(found)
            for found in settled:
                refusal = self._wire(*found)
                if refusal is not None:
                    return refusal
            accepted = True
            return None
        finally:
            if not accepted:
                self.rollback_to(mark)

    def _place(
        self, cell: Any, fp: Footprint, x: int, y: int, rot: int
    ) -> Refusal | None:
        settled = self._settle(cell, fp, x, y, rot)
        if isinstance(settled, Refusal):
            return settled
        return self._wire(*settled)

    def _settle(
        self, cell: Any, fp: Footprint, x: int, y: int, rot: int
    ) -> Refusal | tuple[Any, ...]:
        """The placement without its wiring: the cell inspected, what it rips or displaces taken out, its cells occupied and its pins tabled; what ``_wire`` needs, or the refusal."""
        cells = footprint_cells(x, y, fp.width, fp.height, rot)
        layers = self.layers_for(fp)
        failures, ripped, displaced = inspect(self, cell, fp, x, y, rot, cells, layers)
        if failures:
            return self.physics.diagnose(self, tuple(failures))
        trimmed = [net_id for net_id in ripped if self.trim(net_id, cells)]
        for net_id in ripped:
            if net_id not in trimmed:
                self.unroute(net_id)
        gone = [self.units[unit_id] for unit_id in displaced]
        for unit_id in displaced:
            self.remove_unit(unit_id)
        self._occupy(layers, cells, f"cell:{cell.id}")
        placement = Placement(cell=cell.id, x=x, y=y, rot=rot)
        self.placements[cell.id] = placement
        self.table_cell(cell.id)
        self._record(
            lambda: (self.untable_cell(cell.id), self.placements.pop(cell.id, None))
        )
        legal = self.physics.boundaries.legal(self, placement)
        if legal is not None:
            return legal
        return (cell, cells, ripped, trimmed, gone, displaced)

    def _wire(
        self,
        cell: Any,
        cells: Any,
        ripped: list[str],
        trimmed: list[str],
        gone: list[Any],
        displaced: Any,
    ) -> Refusal | None:
        """Route the nets a settled cell makes routable, grow the routed ones to its pins, cover its needs and put back what it displaced."""
        if self.router is not None:
            grown = [*trimmed, *(n.id for n in self.grown_nets(cell.id))]
            pending = [*ripped, *grown, *(n.id for n in self.ready_nets(cell.id))]
            together = getattr(self.router, "route_all", None)
            if together is not None:
                refusal = together(self, cell.id, pending, set(grown))
                if refusal is not None:
                    return refusal
            else:
                order = getattr(self.router, "order", None)
                ordered = (
                    order(self, cell.id, pending, set(grown))
                    if order is not None
                    else sorted(dict.fromkeys(pending), key=self.span, reverse=True)
                )
                for net_id in ordered:
                    refusal = self.route(net_id, grow=net_id in grown)
                    if refusal is not None:
                        return refusal
        refusal = cover(self, cell, cells)
        if refusal is not None:
            return refusal
        if displaced:
            return recover(self, gone)
        return None

    def span(self, net_id: str) -> int:
        """How far a net's terminals lie apart: the widest Manhattan distance between any two of its placed attach cells."""
        cells = [
            xy
            for ref in self.netlist.nets[net_id].pins()
            if (xy := self.attach_cell(ref.cell, ref.pin)) is not None
        ]
        return max(
            (abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in cells for b in cells),
            default=0,
        )

    def place_instance(
        self, instance_id: str, x: int, y: int, rot: int = 0
    ) -> Refusal | None:
        """Place every leaf of an instance where its macro's fragment puts it, all settled before any of them is wired so no leaf's wire covers a later leaf's port; refuse as one."""
        source = self.problem.netlist
        cell = source.cells.get(instance_id)
        if cell is None or not cell.is_instance:
            raise StateError(f"{instance_id!r} is not an instance of the problem")
        anchor = Placement(cell=instance_id, x=x, y=y, rot=rot)
        flat = Layout(instances={instance_id: anchor}).flatten(source)
        pre_digest = self.digest() if self.checker is not None else ""
        mark = self.mark()
        refusal = self._place_leaves(instance_id, flat)
        if refusal is not None:
            self.rollback_to(mark)
        if self.checker is not None:
            self.checker.on_place(
                self, instance_id, Anchor(x=x, y=y, rot=rot), refusal, pre_digest
            )
        if refusal is not None:
            return refusal
        for wire in flat.wires.values():
            if wire.net not in self.wires:
                self.set_wire(wire)
        previous = self.instance_anchors.get(instance_id)
        self.instance_anchors[instance_id] = anchor
        self._record(lambda: self._restore_anchor(instance_id, previous))
        return None

    def _place_leaves(self, instance_id: str, flat: Layout) -> Refusal | None:
        """Settle every leaf of the instance in name order, then wire each; the first refusal."""
        settled: list[tuple[Any, ...]] = []
        for leaf_id, leaf in sorted(flat.placements.items()):
            leaf_cell = self.netlist.cells.get(leaf_id)
            fp = self.footprint_of(leaf_id)
            if leaf_cell is None or fp is None:
                raise StateError(f"{leaf_id!r} is not a leaf cell of the problem")
            if leaf_id in self.placements:
                raise StateError(f"{leaf_id!r} is already placed")
            found = self._settle(leaf_cell, fp, leaf.x, leaf.y, leaf.rot)
            if isinstance(found, Refusal):
                return found
            settled.append(found)
            self.membership[leaf_id] = instance_id
            self._record(lambda leaf_id=leaf_id: self.membership.pop(leaf_id, None))
        for found in settled:
            refusal = self._wire(*found)
            if refusal is not None:
                return refusal
        return None

    def _restore_anchor(self, instance_id: str, previous: Placement | None) -> None:
        self._tables = None
        if previous is None:
            self.instance_anchors.pop(instance_id, None)
        else:
            self.instance_anchors[instance_id] = previous

    def withdraw(self, cell_id: str) -> None:
        placement = self.placements.get(cell_id)
        fp = self.footprint_of(cell_id)
        if placement is None or fp is None:
            raise StateError(f"{cell_id!r} is not placed")
        for net in self.nets_of(cell_id):
            if net.id in self.wires:
                self.unroute(net.id)
        cells = footprint_cells(
            placement.x, placement.y, fp.width, fp.height, placement.rot
        )
        self._free(self.layers_for(fp), cells, f"cell:{cell_id}")
        self.untable_cell(cell_id)
        del self.placements[cell_id]
        self._record(
            lambda: (
                self.placements.__setitem__(cell_id, placement),
                self.table_cell(cell_id),
            )
        )
        if cell_id in self.membership:
            instance = self.membership.pop(cell_id)
            self._record(lambda: self.membership.__setitem__(cell_id, instance))
            if instance not in self.membership.values():
                anchor = self.instance_anchors.pop(instance, None)
                if anchor is not None:
                    self._record(
                        lambda: self.instance_anchors.__setitem__(instance, anchor)
                    )


__all__ = ["PlacingMixin"]
