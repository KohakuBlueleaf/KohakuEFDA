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
    Placement,
    Refusal,
    Reservation,
    Unit,
    Wire,
)
from kohakulayout.ir.base import digest_of_text
from kohakulayout.ir.geometry import XY, footprint_cells
from kohakulayout.physics.fields import reach_cells
from kohakulayout.physics.protocol import Anchor, Occupant, UnitPlacement
from kohakulayout.state.attach import AttachMixin, Tables
from kohakulayout.state.chain import displaceable, port_shut
from kohakulayout.state.forms import freeze, load
from kohakulayout.state.kernel import Kernel, ShareTable, holder_kind, make_kernel
from kohakulayout.state.placing import PlacingMixin
from kohakulayout.state.router.native_route import native_admits
from kohakulayout.state.snapshot import Token
from kohakulayout.state.transaction import Transaction
from kohakulayout.state.wiring import WiringMixin


class World(AttachMixin, WiringMixin, PlacingMixin):
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
        self._attach_memo: dict[str, tuple[Placement, dict[str, tuple]]] = {}
        self._net_by_pin: dict[tuple[str, str], str] = {
            (r.cell, r.pin): n.id for n in self.netlist.nets.values() for r in n.pins()
        }
        self._tables: Tables | None = None
        self._retabled: set[str] = set()
        self._retable_all = True
        self.native_attempts = True
        self.report_frontier = False
        self._coverage: dict[str, frozenset[XY]] = {}
        self._nets_by_cell: dict[str, list[Any]] | None = None
        self.units_rev = 0
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
        """The holder that forbids ``occupant`` on the cell, or None when it may enter; a reservation of a carrier admits that carrier's wires and every unit (a crossing or junction of one carrier stands where another's wires run, a field's emitter stands until a wire displaces it); a reservation without a carrier admits nothing."""
        for holder in self.kernel.holders_at(layer, xy):
            other = self.occupant_of(holder)
            if other.kind == "reserve":
                if other.carrier is not None and (
                    occupant.kind == "unit" or other.carrier == occupant.carrier
                ):
                    continue
                return holder
            if not self.share.may_share(other, occupant):
                return holder
        return None

    def anchors(self, cell_id: str) -> Iterable[Anchor]:
        cell = self.netlist.cells[cell_id]
        return self.physics.boundaries.anchors(self, cell)

    def anchor_rows(self, cell_id: str) -> Iterable[tuple[int, int, int]]:
        """The cell's anchors as ``(x, y, rot)`` rows: the boundaries' own rows when they give them."""
        cell = self.netlist.cells[cell_id]
        rows = getattr(self.physics.boundaries, "anchor_rows", None)
        if rows is not None:
            return rows(self, cell)
        return ((a.x, a.y, a.rot) for a in self.physics.boundaries.anchors(self, cell))

    def admits(
        self,
        cell_id: str,
        x: int,
        y: int,
        rot: int = 0,
        owners: dict[str, dict[XY, str]] | None = None,
    ) -> bool:
        """Whether the footprint covers nothing it could not displace (wires and route units a router re-routes, emitters placed again) and no port is shut; the cheap half of ``place``."""
        cell = self.netlist.cells.get(cell_id)
        fp = self.footprint_of(cell_id)
        if cell is None or fp is None or rot not in fp.rotations:
            return False
        if self.checker is None and self.native_attempts:
            native = native_admits(self, cell, fp, x, y, rot)
            if native is not None:
                return native
        cells = footprint_cells(x, y, fp.width, fp.height, rot)
        if not all(self.in_grid(c) for c in cells):
            return False
        layers = self.layers_for(fp)
        for layer in layers:
            for xy in cells:
                for holder in self.kernel.holders_at(layer, xy):
                    if displaceable(self, *holder_kind(holder)) is None:
                        return False
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
        """The cells the field's emitters reach; kept until a unit comes or goes."""
        hit = self._coverage.get(kind)
        if hit is not None:
            return hit
        emitters = {e.footprint.id: e for e in self.physics.fields.emitters()}
        covered: set[XY] = set()
        for unit in self.units.values():
            emitter = emitters.get(unit.footprint)
            if unit.owner == f"field:{kind}" and emitter is not None:
                covered |= reach_cells(emitter, unit.x, unit.y)
        self._coverage[kind] = frozenset(covered)
        return self._coverage[kind]

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

    def record(self, undo: Any) -> None:
        """Log an undo step of a collaborator's state, so a rollback reverts it with the world's."""
        self._record(undo)

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

    def _write_runs(
        self,
        holder: str,
        runs: dict[str, list[tuple[XY, int]]],
        before: dict[str, list[tuple[XY, int]]],
    ) -> None:
        """Write a holder's runs per layer over ``before``; the undo writes ``before`` back."""
        for layer in sorted(set(runs) | set(before)):
            new, old = dict(runs.get(layer, ())), dict(before.get(layer, ()))
            cells = sorted(set(new) | set(old))
            self.kernel.set_runs(layer, holder, [(xy, new.get(xy, 0)) for xy in cells])
            self._record(
                lambda layer=layer, old=old, cells=cells: self.kernel.set_runs(
                    layer, holder, [(xy, old.get(xy, 0)) for xy in cells]
                )
            )

    # ---------------------------------------------------------------- units
    def place_unit(
        self, spot: UnitPlacement, unit_id: str | None = None
    ) -> Refusal | None:
        """Hold a unit's cells; only a swept field's emitter may cover another pin's open attach cell, and none covers an attach cell claimed by an unreached pin of another net."""
        fp = spot.footprint
        cells = footprint_cells(spot.x, spot.y, fp.width, fp.height, spot.rot)
        layers = self.layers_for(fp)
        if not all(self.in_grid(c) for c in cells):
            return Refusal(
                stage="region", subject=f"unit:{spot.kind}", detail="leaves the grid"
            )
        mine = spot.owner.removeprefix("net:")
        net = self.netlist.nets.get(mine)
        occupant = Occupant(
            kind="unit", unit_kind=spot.kind, carrier=net.carrier if net else None
        )
        owners = self.open_attach_owners()
        claims = self.claimed_attach_owners()
        emitter = spot.owner.startswith("field:") and self.physics.fields.sweep(
            spot.kind
        )
        for layer in layers:
            for xy in cells:
                owner = owners.get(layer, {}).get(xy)
                if owner is not None and owner != mine and not emitter:
                    return Refusal(
                        stage="port_shut",
                        subject=f"unit:{spot.kind}",
                        detail=f"covers the attach cell {xy} of a pin of {owner}",
                    )
                nets = claims.get(layer, {}).get(xy)
                if nets and mine not in nets and not emitter:
                    return Refusal(
                        stage="port_shut",
                        subject=f"unit:{spot.kind}",
                        detail=f"covers the attach cell {xy} claimed by {min(nets)}",
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
        self._unit_changed(unit.owner.startswith("field:"))
        self._record(
            lambda: (
                self.units.pop(unit_id, None),
                self._unit_changed(unit.owner.startswith("field:")),
            )
        )
        self.library.setdefault(fp.id, fp)
        self.kernel.note_unit(
            unit_id,
            fp.id,
            mine if spot.owner.startswith("net:") else "",
            spot.owner.startswith("field:"),
        )
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
        self._unit_changed(unit.owner.startswith("field:"))
        self._record(
            lambda: (
                self.units.__setitem__(unit_id, unit),
                self._unit_changed(unit.owner.startswith("field:")),
            )
        )

    def _unit_changed(self, field: bool) -> None:
        """A unit came or went: the unit tables the searches cache are stale, and a field's coverage with it."""
        self.units_rev += 1
        if field:
            self._coverage.clear()

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
        self._tables = None
        self._unit_changed(True)
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
        self._tables = None
        self._unit_changed(True)
        if self._tx is not None and self._tx.open:
            raise StateError("load inside an open transaction")
        load(self, layout)
        self.revision += 1
        self.forget_routes()
