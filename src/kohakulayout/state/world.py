"""The world: the live, transactional L2 every solver mutates through the builder.

Every mutation happens inside a transaction and is journaled for rollback. A refused
``place`` or ``route`` leaves the digest unchanged. The world interprets no kind and no
attr: it asks the physics for anchors, legality, sharing, cover and diagnosis.
"""

from collections.abc import Iterable
from typing import Any

from kohakulayout.errors import StateError
from kohakulayout.ir import (
    Footprint,
    Layout,
    Net,
    Placement,
    Refusal,
    Reservation,
    Unit,
    Wire,
)
from kohakulayout.ir.base import digest_of_text
from kohakulayout.ir.geometry import ROTATIONS, XY, attach_cell, footprint_cells
from kohakulayout.physics.fields import reach_cells
from kohakulayout.physics.protocol import Anchor, Occupant, UnitPlacement
from kohakulayout.state.chain import cover, inspect, port_shut
from kohakulayout.state.forms import freeze, load
from kohakulayout.state.kernel import Kernel, ShareTable, holder_kind, make_kernel
from kohakulayout.state.snapshot import Token
from kohakulayout.state.transaction import Transaction


class World:
    def __init__(
        self,
        problem: Any,
        physics: Any,
        kernel: str | Kernel = "python",
        router: Any = None,
    ) -> None:
        self.problem = problem
        self.physics = physics
        self.fabric = problem.fabric
        self.netlist = problem.netlist.flatten()
        self.library: dict[str, Footprint] = {
            **physics.unit_footprints(),
            **self.netlist.library,
        }
        fabric = self.fabric
        self.kernel: Kernel = (
            make_kernel(kernel, fabric.width, fabric.height, tuple(fabric.layers))
            if isinstance(kernel, str)
            else kernel
        )
        self.router = router
        self.share = ShareTable(physics.carriers)
        self.build_cells: frozenset[XY] = fabric.build_cells()
        self.placements: dict[str, Placement] = {}
        self.wires: dict[str, Wire] = {}
        self.units: dict[str, Unit] = {}
        self.reservations: dict[str, Reservation] = {}
        self.membership: dict[str, str] = {}
        self.instance_anchors: dict[str, Placement] = {}
        self.checker: Any = None
        self.seq = 0
        self.revision = 0
        self._digest: tuple[int, str] | None = None
        self._tx: Transaction | None = None
        self._unit_seq = 0

    # ------------------------------------------------------------ helpers
    def footprint_of(self, cell_id: str) -> Footprint | None:
        return self.netlist.footprint_for(cell_id)

    def in_grid(self, xy: XY) -> bool:
        return self.fabric.in_grid(*xy)

    def in_build(self, xy: XY) -> bool:
        return xy in self.build_cells

    @staticmethod
    def layers_for(fp: Footprint) -> tuple[str, ...]:
        return (fp.layer, *fp.occludes)

    def free_footprint(self, fp: Footprint, x: int, y: int, rot: int) -> bool:
        cells = footprint_cells(x, y, fp.width, fp.height, rot)
        if not all(self.in_grid(c) for c in cells):
            return False
        return all(self.kernel.free_for(layer, cells) for layer in self.layers_for(fp))

    def free_for(self, footprint_id: str, x: int, y: int, rot: int) -> bool:
        fp = self.library.get(footprint_id)
        return fp is not None and self.free_footprint(fp, x, y, rot)

    def carrier_layer(self, carrier: str) -> str:
        found = self.fabric.carriers.get(carrier)
        return found.layer if found is not None else self.fabric.layers[0]

    def occupant_of(self, holder: str) -> Occupant:
        kind, ref = holder_kind(holder)
        if kind == "wire":
            net = self.netlist.nets.get(ref)
            return Occupant(kind="wire", carrier=net.carrier if net else None, id=ref)
        if kind == "unit":
            unit = self.units.get(ref)
            return Occupant(kind="unit", unit_kind=unit.kind if unit else None, id=ref)
        if kind == "reserve":
            reservation = self.reservations.get(ref)
            return Occupant(
                kind="reserve",
                carrier=reservation.carrier if reservation else None,
                id=ref,
            )
        return Occupant(kind="cell", id=ref)

    def may_occupy(self, layer: str, xy: XY, occupant: Occupant) -> str | None:
        """The holder that forbids ``occupant`` on the cell, or None when it may enter."""
        for holder in self.kernel.holders_at(layer, xy):
            other = self.occupant_of(holder)
            if other.kind == "reserve":
                if (
                    occupant.kind == "wire"
                    and other.carrier is not None
                    and other.carrier == occupant.carrier
                ):
                    continue
                return holder
            if not self.share.may_share(other, occupant):
                return holder
        return None

    def attach_cells(self, cell_id: str) -> dict[str, XY]:
        """Every pin's attach cell for a placed cell, through each pin's first allowed port."""
        placement = self.placements.get(cell_id)
        fp = self.footprint_of(cell_id)
        if placement is None or fp is None:
            return {}
        out: dict[str, XY] = {}
        for pin in self.netlist.pins_of(cell_id):
            port = fp.port(pin.ports[0]) if pin.ports else None
            if port is None:
                continue
            ax, ay = attach_cell(
                fp.width, fp.height, port.side, port.offset, placement.rot
            )
            out[pin.id] = (placement.x + ax, placement.y + ay)
        return out

    def attach_cell(self, cell_id: str, pin_id: str) -> XY | None:
        return self.attach_cells(cell_id).get(pin_id)

    def nets_of(self, cell_id: str) -> tuple[Net, ...]:
        return tuple(
            n
            for n in self.netlist.nets.values()
            if any(r.cell == cell_id for r in n.pins())
        )

    def ready(self, net: Net) -> bool:
        return all(r.cell in self.placements for r in net.pins())

    def ready_nets(self, cell_id: str) -> tuple[Net, ...]:
        return tuple(
            n for n in self.nets_of(cell_id) if self.ready(n) and n.id not in self.wires
        )

    def unrouted(self) -> tuple[Net, ...]:
        return tuple(n for n in self.netlist.nets.values() if n.id not in self.wires)

    def anchors(self, cell_id: str) -> Iterable[Anchor]:
        cell = self.netlist.cells[cell_id]
        return self.physics.boundaries.anchors(self, cell)

    def open_attach_owners(self) -> dict[str, dict[XY, str]]:
        """Per layer, the net owning each attach cell of a placed pin whose net is still unrouted."""
        out: dict[str, dict[XY, str]] = {}
        for net in self.unrouted():
            for ref in net.pins():
                attach = self.attach_cell(ref.cell, ref.pin)
                if attach is not None:
                    out.setdefault(self.carrier_layer(net.carrier), {})[attach] = net.id
        return out

    def open_attach_cells(self) -> dict[str, frozenset[XY]]:
        """Per layer, the attach cells of every placed pin whose net is still unrouted."""
        return {
            layer: frozenset(owners)
            for layer, owners in self.open_attach_owners().items()
        }

    def admits(
        self,
        cell_id: str,
        x: int,
        y: int,
        rot: int = 0,
        owners: dict[str, dict[XY, str]] | None = None,
    ) -> bool:
        """Whether the footprint is free there and no port is shut; the cheap half of ``place``."""
        cell = self.netlist.cells.get(cell_id)
        fp = self.footprint_of(cell_id)
        if cell is None or fp is None or rot not in fp.rotations:
            return False
        if not self.free_footprint(fp, x, y, rot):
            return False
        cells = footprint_cells(x, y, fp.width, fp.height, rot)
        layers = self.layers_for(fp)
        return not port_shut(self, cell, fp, x, y, rot, cells, layers, owners)

    def first_open(
        self, cell_id: str, anchors: Iterable[Anchor] | None = None
    ) -> Anchor | None:
        """The first anchor whose footprint is free and covers no open attach cell."""
        fp = self.footprint_of(cell_id)
        if fp is None:
            return None
        owners = self.open_attach_owners()
        for anchor in anchors if anchors is not None else self.anchors(cell_id):
            if self.admits(cell_id, anchor.x, anchor.y, anchor.rot, owners):
                return anchor
        return None

    def extent(self, region: str = "build") -> tuple[int, int, int, int]:
        mask = (
            self.fabric.regions[region].cells()
            if region in self.fabric.regions
            else None
        )
        return self.kernel.extent(None, mask) or (0, 0, 0, 0)

    def occupancy(self, layer: str) -> Any:
        return self.kernel.occupancy(layer)

    def field_coverage(self, kind: str) -> frozenset[XY]:
        emitters = {e.footprint.id: e for e in self.physics.fields.emitters()}
        covered: set[XY] = set()
        for unit in self.units.values():
            emitter = emitters.get(unit.footprint)
            if unit.owner == f"field:{kind}" and emitter is not None:
                covered |= reach_cells(emitter, unit.x, unit.y)
        return frozenset(covered)

    # ------------------------------------------------------- transactions
    def transaction(self) -> Transaction:
        if self._tx is not None and self._tx.open:
            raise StateError("a transaction is already open; use marks inside one")
        self._tx = Transaction(self)
        return self._tx

    def _require_tx(self) -> Transaction:
        if self._tx is None or not self._tx.open:
            raise StateError("a mutation outside a transaction")
        return self._tx

    def _record(self, undo: Any) -> None:
        self._require_tx().record(undo)
        self.seq += 1
        self.revision += 1

    def mark(self) -> int:
        return self._require_tx().mark()

    def rollback_to(self, mark: int) -> None:
        self._require_tx().rollback_to(mark)
        self.revision += 1

    # ---------------------------------------------------------- occupancy
    def _occupy(
        self, layers: Iterable[str], cells: tuple[XY, ...], holder: str
    ) -> None:
        for layer in layers:
            self.kernel.occupy(layer, cells, holder)
            self._record(lambda layer=layer: self.kernel.free(layer, cells, holder))

    def _free(self, layers: Iterable[str], cells: tuple[XY, ...], holder: str) -> None:
        for layer in layers:
            self.kernel.free(layer, cells, holder)
            self._record(lambda layer=layer: self.kernel.occupy(layer, cells, holder))

    # ---------------------------------------------------------- placement
    def place(self, cell_id: str, x: int, y: int, rot: int = 0) -> Refusal | None:
        """Place a leaf cell, route the nets it completes, cover its needs; refuse and roll back otherwise."""
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

    def _place(
        self, cell: Any, fp: Footprint, x: int, y: int, rot: int
    ) -> Refusal | None:
        cells = footprint_cells(x, y, fp.width, fp.height, rot)
        layers = self.layers_for(fp)
        failures, ripped = inspect(self, cell, fp, x, y, rot, cells, layers)
        if failures:
            return self.physics.diagnose(self, tuple(failures))
        for net_id in ripped:
            self.unroute(net_id)
        self._occupy(layers, cells, f"cell:{cell.id}")
        placement = Placement(cell=cell.id, x=x, y=y, rot=rot)
        self.placements[cell.id] = placement
        self._record(lambda: self.placements.pop(cell.id, None))
        legal = self.physics.boundaries.legal(self, placement)
        if legal is not None:
            return legal
        refusal = cover(self, cell, cells)
        if refusal is not None:
            return refusal
        if self.router is not None:
            for net_id in [*ripped, *(n.id for n in self.ready_nets(cell.id))]:
                refusal = self.route(net_id)
                if refusal is not None:
                    return refusal
        return None

    def place_instance(
        self, instance_id: str, x: int, y: int, rot: int = 0
    ) -> Refusal | None:
        """Place every leaf of an instance where its macro's fragment puts it; refuse as one."""
        source = self.problem.netlist
        cell = source.cells.get(instance_id)
        if cell is None or not cell.is_instance:
            raise StateError(f"{instance_id!r} is not an instance of the problem")
        anchor = Placement(cell=instance_id, x=x, y=y, rot=rot)
        flat = Layout(instances={instance_id: anchor}).flatten(source)
        mark = self.mark()
        for leaf_id, leaf in sorted(flat.placements.items()):
            refusal = self.place(leaf_id, leaf.x, leaf.y, leaf.rot)
            if refusal is not None:
                self.rollback_to(mark)
                return refusal
            self.membership[leaf_id] = instance_id
            self._record(lambda leaf_id=leaf_id: self.membership.pop(leaf_id, None))
        for wire in flat.wires.values():
            if wire.net not in self.wires:
                self.set_wire(wire)
        previous = self.instance_anchors.get(instance_id)
        self.instance_anchors[instance_id] = anchor
        self._record(lambda: self._restore_anchor(instance_id, previous))
        return None

    def _restore_anchor(self, instance_id: str, previous: Placement | None) -> None:
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
        del self.placements[cell_id]
        self._record(lambda: self.placements.__setitem__(cell_id, placement))
        if cell_id in self.membership:
            instance = self.membership.pop(cell_id)
            self._record(lambda: self.membership.__setitem__(cell_id, instance))
            if instance not in self.membership.values():
                anchor = self.instance_anchors.pop(instance, None)
                if anchor is not None:
                    self._record(
                        lambda: self.instance_anchors.__setitem__(instance, anchor)
                    )

    # ---------------------------------------------------------------- units
    def place_unit(
        self, spot: UnitPlacement, unit_id: str | None = None
    ) -> Refusal | None:
        fp = spot.footprint
        cells = footprint_cells(spot.x, spot.y, fp.width, fp.height, spot.rot)
        layers = self.layers_for(fp)
        if not all(self.in_grid(c) for c in cells):
            return Refusal(
                stage="region", subject=f"unit:{spot.kind}", detail="leaves the grid"
            )
        occupant = Occupant(kind="unit", unit_kind=spot.kind)
        owners = self.open_attach_owners()
        mine = spot.owner.removeprefix("net:")
        for layer in layers:
            for xy in cells:
                owner = owners.get(layer, {}).get(xy)
                if owner is not None and owner != mine:
                    return Refusal(
                        stage="port_shut",
                        subject=f"unit:{spot.kind}",
                        detail=f"covers the attach cell {xy} of a pin of {owner}",
                    )
                blocker = self.may_occupy(layer, xy, occupant)
                if blocker is not None:
                    return Refusal(
                        stage="overlap",
                        subject=f"unit:{spot.kind}",
                        detail=f"{blocker} holds {xy} on {layer}",
                        attrs={"kl": {"holder": blocker}},
                    )
        if unit_id is None:
            unit_id = self.next_unit_id()
        unit = Unit(
            id=unit_id,
            kind=spot.kind,
            footprint=fp.id,
            x=spot.x,
            y=spot.y,
            rot=spot.rot,
            owner=spot.owner,
        )
        self.units[unit_id] = unit
        self._record(lambda: self.units.pop(unit_id, None))
        self.library.setdefault(fp.id, fp)
        self._occupy(layers, cells, f"unit:{unit_id}")
        return None

    def next_unit_id(self) -> str:
        """A fresh unit id; the counter never rewinds, so a rolled-back unit's id is not reused."""
        self._unit_seq += 1
        while f"u{self._unit_seq}" in self.units:
            self._unit_seq += 1
        return f"u{self._unit_seq}"

    def remove_unit(self, unit_id: str) -> None:
        unit = self.units.get(unit_id)
        if unit is None:
            return
        fp = self.library[unit.footprint]
        cells = footprint_cells(unit.x, unit.y, fp.width, fp.height, unit.rot)
        self._free(self.layers_for(fp), cells, f"unit:{unit_id}")
        del self.units[unit_id]
        self._record(lambda: self.units.__setitem__(unit_id, unit))

    # -------------------------------------------------------------- routing
    def route(self, net_id: str) -> Refusal | None:
        if net_id not in self.netlist.nets:
            raise StateError(f"no net {net_id!r}")
        if net_id in self.wires:
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
        forget = getattr(self.router, "forget", None)
        if forget is not None:
            forget()

    def set_wire(self, wire: Wire) -> None:
        """Record a routed wire and hold its cells; the router calls this after finding a path."""
        for segment in wire.segments:
            self._occupy((segment.layer,), tuple(segment.cells), f"wire:{wire.net}")
        self.wires[wire.net] = wire
        self._record(lambda: self.wires.pop(wire.net, None))

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
        self._record(lambda: self.wires.__setitem__(net_id, wire))
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

    # --------------------------------------------------------- reservations
    def reserve(
        self, tag: str, layer: str, cells: Iterable[XY], carrier: str | None = None
    ) -> None:
        if tag in self.reservations:
            raise StateError(f"reservation {tag!r} exists")
        reservation = Reservation(
            tag=tag, layer=layer, cells=tuple(sorted(cells)), carrier=carrier
        )
        self.reservations[tag] = reservation
        self._record(lambda: self.reservations.pop(tag, None))
        self._occupy((layer,), reservation.cells, f"reserve:{tag}")

    def release(self, tag: str) -> None:
        reservation = self.reservations.get(tag)
        if reservation is None:
            return
        self._free((reservation.layer,), reservation.cells, f"reserve:{tag}")
        del self.reservations[tag]
        self._record(lambda: self.reservations.__setitem__(tag, reservation))

    # -------------------------------------------------- snapshots and forms
    def freeze(self, hierarchical: bool = False) -> Layout:
        return freeze(self, hierarchical)

    def digest(self) -> str:
        """The digest of the frozen layout, kept until the next mutation."""
        if self._digest is None or self._digest[0] != self.revision:
            self._digest = (self.revision, digest_of_text(self.freeze().to_json()))
        return self._digest[1]

    def snapshot(self) -> Token:
        return Token(
            seq=self.seq,
            placements=dict(self.placements),
            wires=dict(self.wires),
            units=dict(self.units),
            reservations=tuple(self.reservations.values()),
            membership=dict(self.membership),
            kernel=self.kernel.save(),
            digest=self.digest(),
        )

    def restore(self, token: Token) -> None:
        if self._tx is not None and self._tx.open:
            raise StateError(
                "restore inside an open transaction; roll back to a mark instead"
            )
        kernel = self.kernel
        kernel.load(token.kernel)
        self.forget_routes()
        self.placements = dict(token.placements)
        self.wires = dict(token.wires)
        self.units = dict(token.units)
        self.reservations = {r.tag: r for r in token.reservations}
        self.membership = dict(token.membership)
        self.seq = token.seq
        self.revision += 1
        if self.checker is not None:
            self.checker.on_restore(self, token, kernel)

    def load(self, layout: Layout) -> None:
        """Adopt a frozen layout wholesale, without checks; a verified layout is the caller's job."""
        if self._tx is not None and self._tx.open:
            raise StateError("load inside an open transaction")
        load(self, layout)
        self.revision += 1
        self.forget_routes()
