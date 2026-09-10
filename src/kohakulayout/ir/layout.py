"""L2: where everything is. Framework vocabulary only; flat by default, instances optional.

The layout does not know footprints or the grid on its own, so ``check`` covers internal
consistency and ``check_against`` covers the geometry once a netlist and a fabric are given.
"""

from typing import Any, ClassVar

from kohakulayout.ir.base import Attrs, Level, Model, Node, check_attrs
from kohakulayout.ir.geometry import (
    ROTATIONS,
    XY,
    Rotation,
    attach_cell,
    bbox,
    connected,
    contiguous,
    footprint_cells,
    rotate_point,
    rotate_size,
)

OWNER_KINDS: tuple[str, ...] = ("net", "field", "cell")


class Placement(Model):
    cell: str
    x: int
    y: int
    rot: Rotation = 0


class Segment(Model):
    carrier: str
    layer: str
    cells: tuple[XY, ...]


class Wire(Model):
    net: str
    segments: tuple[Segment, ...] = ()
    units: tuple[str, ...] = ()
    ports: dict[str, str] = {}

    def port_of(self, ref: Any) -> str | None:
        """The port this wire uses at a pin, recorded for every pin that may use more than one."""
        return self.ports.get(str(ref))

    def cells(self) -> frozenset[XY]:
        out: set[XY] = set()
        for segment in self.segments:
            out.update(segment.cells)
        return frozenset(out)


class Unit(Node):
    footprint: str
    x: int
    y: int
    rot: Rotation = 0
    owner: str = ""


class Reservation(Model):
    tag: str
    layer: str
    cells: tuple[XY, ...]
    carrier: str | None = None


def _shift_placement(
    placement: Placement,
    ox: int,
    oy: int,
    width: int,
    height: int,
    rot: int,
    fp_w: int,
    fp_h: int,
) -> Placement:
    """A fragment placement re-anchored after the fragment rotates by ``rot`` and moves to ``(ox, oy)``."""
    cells = footprint_cells(placement.x, placement.y, fp_w, fp_h, placement.rot)
    moved = [rotate_point(px, py, width, height, rot) for px, py in cells]
    min_x = min(c[0] for c in moved)
    min_y = min(c[1] for c in moved)
    new_rot = (placement.rot + rot) % 360
    return Placement(cell=placement.cell, x=ox + min_x, y=oy + min_y, rot=new_rot)


class Layout(Level):
    level: ClassVar[str] = "layout"
    problem: str = ""
    placements: dict[str, Placement] = {}
    instances: dict[str, Placement] = {}
    wires: dict[str, Wire] = {}
    units: dict[str, Unit] = {}
    reservations: tuple[Reservation, ...] = ()
    attrs: Attrs = {}

    @property
    def is_flat(self) -> bool:
        return not self.instances

    def check(self) -> list[str]:
        problems: list[str] = []
        for key, placement in {**self.placements, **self.instances}.items():
            if key != placement.cell:
                problems.append(
                    f"layout: placement key {key!r} names {placement.cell!r}"
                )
            if placement.rot not in ROTATIONS:
                problems.append(f"layout: {key} has rotation {placement.rot}")
        for key, wire in self.wires.items():
            if key != wire.net:
                problems.append(f"layout: wire key {key!r} names {wire.net!r}")
            for i, segment in enumerate(wire.segments):
                if not segment.cells:
                    problems.append(f"wire {key}: segment {i} is empty")
                elif not contiguous(segment.cells):
                    problems.append(f"wire {key}: segment {i} is not a contiguous path")
            if wire.segments and not connected(wire.cells()):
                problems.append(
                    f"wire {key}: its segments do not form one connected tree"
                )
            for unit_id in wire.units:
                if unit_id not in self.units:
                    problems.append(f"wire {key}: unit {unit_id!r} does not exist")
        for key, unit in self.units.items():
            if key != unit.id:
                problems.append(f"layout: unit key {key!r} names {unit.id!r}")
            kind, _, ref = unit.owner.partition(":")
            if kind not in OWNER_KINDS or not ref:
                problems.append(
                    f"unit {key}: owner {unit.owner!r} is not net:, field: or cell:"
                )
            problems += check_attrs(unit.attrs, f"unit {key}")
        for reservation in self.reservations:
            if not reservation.cells:
                problems.append(f"reservation {reservation.tag}: no cells")
        problems += check_attrs(self.attrs, "layout")
        return problems

    def placed(self, cell: str) -> Placement | None:
        return self.placements.get(cell)

    def attach(self, netlist: Any, ref: Any, port_id: str | None = None) -> XY | None:
        """The attach cell of a placed pin through ``port_id``, else its first allowed port; None when unplaced."""
        placement = self.placements.get(ref.cell)
        fp = netlist.footprint_for(ref.cell)
        pin = netlist.pin(ref)
        if placement is None or fp is None or pin is None or not pin.ports:
            return None
        port = fp.port(port_id if port_id in pin.ports else pin.ports[0])
        if port is None:
            return None
        ax, ay = attach_cell(fp.width, fp.height, port.side, port.offset, placement.rot)
        return (placement.x + ax, placement.y + ay)

    def check_against(self, netlist: Any, fabric: Any = None) -> list[str]:
        """Geometry: cells in the grid, no footprint overlap per layer, wires at their pins.

        Without a fabric the grid and the carriers are not checked, which is how a macro
        fragment is verified.
        """
        problems: list[str] = []
        flat_netlist = netlist.flatten()
        occupied: dict[str, dict[XY, str]] = {}
        for key, placement in self.placements.items():
            cell = flat_netlist.cells.get(key)
            fp = flat_netlist.footprint_for(key)
            if cell is None or fp is None:
                problems.append(f"layout: {key} is not a leaf cell of the netlist")
                continue
            if placement.rot not in fp.rotations:
                problems.append(
                    f"layout: {key} is rotated by {placement.rot}, which {fp.id} forbids"
                )
            for layer in (fp.layer, *fp.occludes):
                for xy in footprint_cells(
                    placement.x, placement.y, fp.width, fp.height, placement.rot
                ):
                    if fabric is not None and not fabric.in_grid(*xy):
                        problems.append(f"layout: {key} leaves the grid at {xy}")
                        break
                    holder = occupied.setdefault(layer, {}).get(xy)
                    if holder is not None and holder != key:
                        problems.append(
                            f"layout: {key} overlaps {holder} at {xy} on {layer}"
                        )
                        break
                    occupied[layer][xy] = key
        for key in self.instances:
            cell = netlist.cells.get(key)
            if cell is None or cell.macro is None:
                problems.append(f"layout: instance {key} is not a macro instance")
        for key, wire in self.wires.items():
            net = flat_netlist.nets.get(key)
            if net is None:
                problems.append(f"wire {key}: no such net")
                continue
            carrier = fabric.carriers.get(net.carrier) if fabric is not None else None
            for segment in wire.segments:
                if segment.carrier != net.carrier:
                    problems.append(
                        f"wire {key}: segment carrier {segment.carrier!r} is not {net.carrier!r}"
                    )
                if carrier is not None and segment.layer != carrier.layer:
                    problems.append(
                        f"wire {key}: segment layer {segment.layer!r} is not {carrier.layer!r}"
                    )
                for xy in segment.cells:
                    if fabric is not None and not fabric.in_grid(*xy):
                        problems.append(f"wire {key}: cell {xy} is outside the grid")
                        break
            cells = wire.cells()
            for ref in net.pins():
                chosen = wire.port_of(ref)
                pin = flat_netlist.pin(ref)
                if chosen is not None and (pin is None or chosen not in pin.ports):
                    problems.append(f"wire {key}: {ref} may not use port {chosen!r}")
                    continue
                attach = self.attach(flat_netlist, ref, chosen)
                if attach is not None and attach not in cells:
                    problems.append(f"wire {key}: does not reach {ref} at {attach}")
        for key, unit in self.units.items():
            if fabric is not None and not fabric.in_grid(unit.x, unit.y):
                problems.append(f"unit {key}: outside the grid")
        return problems

    def flatten(self, netlist: Any) -> "Layout":
        """Instances expanded into leaf placements, wires and units, ids joined with ``/``."""
        if self.is_flat:
            return self
        placements = dict(self.placements)
        wires = dict(self.wires)
        units = dict(self.units)
        for key, instance in self.instances.items():
            cell = netlist.cells.get(key)
            macro = (
                netlist.macros.get(cell.macro)
                if cell is not None and cell.macro
                else None
            )
            if macro is None or macro.footprint is None:
                continue
            width, height = macro.footprint.width, macro.footprint.height
            prefix = key + "/"
            module = netlist.modules.get(macro.module)
            body = (
                module.body.with_library(netlist).flatten()
                if module is not None
                else None
            )
            for leaf_key, leaf in macro.layout.placements.items():
                fp = body.footprint_for(leaf_key) if body is not None else None
                if fp is None:
                    continue
                moved = _shift_placement(
                    leaf,
                    instance.x,
                    instance.y,
                    width,
                    height,
                    instance.rot,
                    fp.width,
                    fp.height,
                )
                placements[prefix + leaf_key] = Placement(
                    cell=prefix + leaf_key, x=moved.x, y=moved.y, rot=moved.rot
                )
            for wire_key, wire in macro.layout.wires.items():
                segments = tuple(
                    Segment(
                        carrier=s.carrier,
                        layer=s.layer,
                        cells=tuple(
                            (instance.x + rx, instance.y + ry)
                            for rx, ry in (
                                rotate_point(px, py, width, height, instance.rot)
                                for px, py in s.cells
                            )
                        ),
                    )
                    for s in wire.segments
                )
                wires[prefix + wire_key] = Wire(
                    net=prefix + wire_key,
                    segments=segments,
                    units=tuple(prefix + u for u in wire.units),
                    ports={prefix + k: v for k, v in wire.ports.items()},
                )
            for unit_key, unit in macro.layout.units.items():
                rx, ry = rotate_point(unit.x, unit.y, width, height, instance.rot)
                owner_kind, _, owner_ref = unit.owner.partition(":")
                units[prefix + unit_key] = unit.model_copy(
                    update={
                        "id": prefix + unit_key,
                        "x": instance.x + rx,
                        "y": instance.y + ry,
                        "rot": (unit.rot + instance.rot) % 360,
                        "owner": (
                            f"{owner_kind}:{prefix + owner_ref}"
                            if owner_kind != "field"
                            else unit.owner
                        ),
                    }
                )
        return Layout(
            schema_version=self.schema_version,
            problem=self.problem,
            placements=placements,
            wires=wires,
            units=units,
            reservations=self.reservations,
            attrs=self.attrs,
        )

    def extent(self, netlist: Any) -> tuple[int, int, int, int]:
        """``(min_x, min_y, width, height)`` over placed footprints, wires and units."""
        cells: set[XY] = set()
        for key, placement in self.placements.items():
            fp = netlist.footprint_for(key)
            if fp is not None:
                cells.update(
                    footprint_cells(
                        placement.x, placement.y, fp.width, fp.height, placement.rot
                    )
                )
        for wire in self.wires.values():
            cells.update(wire.cells())
        for unit in self.units.values():
            cells.add((unit.x, unit.y))
        if not cells:
            return (0, 0, 0, 0)
        return bbox(frozenset(cells))

    def footprint_extent(self, netlist: Any, key: str) -> tuple[int, int] | None:
        placement = self.placements.get(key)
        fp = netlist.footprint_for(key)
        if placement is None or fp is None:
            return None
        return rotate_size(fp.width, fp.height, placement.rot)
