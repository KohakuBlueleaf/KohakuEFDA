"""What a placed pin attaches to: every allowed port's attach cell per placement, the port a routed wire took, the nets a cell touches, and the attach cells other routes must respect, memoised until placements or wires change."""

from typing import Any

from kohakulayout.ir import Footprint, Net, Pin
from kohakulayout.ir.geometry import XY, attach_cell, port_cell

Choice = tuple[str, XY, XY]


def options_at(fp: Footprint, pin: Pin, x: int, y: int, rot: int) -> tuple[Choice, ...]:
    """Every port the pin may use at an anchor, as (port id, attach cell, port cell), in the pin's order."""
    return tuple(
        (port_id, (x + ax, y + ay), (x + px, y + py))
        for port_id, ax, ay, px, py in _offsets(fp, pin.ports, rot)
    )


_OFFSETS: dict[tuple[int, tuple[str, ...], int], tuple[Footprint, tuple]] = {}


def _offsets(
    fp: Footprint, ports: tuple[str, ...], rot: int
) -> tuple[tuple[str, int, int, int, int], ...]:
    """The attach and port cells of a pin's ports relative to the anchor, read once per footprint, port list and rotation."""
    key = (id(fp), ports, rot)
    hit = _OFFSETS.get(key)
    if hit is not None and hit[0] is fp:
        return hit[1]
    out = []
    for port_id in ports:
        port = fp.port(port_id)
        if port is None:
            continue
        ax, ay = attach_cell(fp.width, fp.height, port.side, port.offset, rot)
        px, py = port_cell(fp.width, fp.height, port.side, port.offset, rot)
        out.append((port_id, ax, ay, px, py))
    _OFFSETS[key] = (fp, tuple(out))
    return _OFFSETS[key][1]


class AttachMixin:
    placements: dict[str, Any]
    wires: dict[str, Any]
    netlist: Any
    _attach_memo: dict
    _nets_by_cell: dict[str, list[Net]] | None
    _tables: "Tables | None"
    _net_by_pin: dict[tuple[str, str], str]

    """The attach-cell views of a world; the world keeps the memos and bumps its counters on every placement or wire change."""

    def port_choices(self, cell_id: str) -> dict[str, tuple[Choice, ...]]:
        """Per pin of a placed cell, every port it may use with its attach and port cells; memoised per placement."""
        placement = self.placements.get(cell_id)
        if placement is None:
            return {}
        hit = self._attach_memo.get(cell_id)
        if hit is not None and hit[0] is placement:
            return hit[1]
        fp = self.footprint_of(cell_id)
        if fp is None:
            return {}
        out: dict[str, tuple[Choice, ...]] = {}
        for pin in self.netlist.pins_of(cell_id):
            choices = options_at(fp, pin, placement.x, placement.y, placement.rot)
            if choices:
                out[pin.id] = choices
        self._attach_memo[cell_id] = (placement, out)
        return out

    def net_of(self, cell_id: str, pin_id: str) -> str | None:
        return self._net_by_pin.get((cell_id, pin_id))

    def routed_port(self, cell_id: str, pin_id: str) -> str | None:
        """The port the pin's wire uses: the one recorded, else a pin's only port; None while its net is unrouted or its wire has not reached a pin with a choice."""
        net_id = self._net_by_pin.get((cell_id, pin_id))
        wire = self.wires.get(net_id) if net_id is not None else None
        if wire is None:
            return None
        chosen = wire.ports.get(f"{cell_id}.{pin_id}")
        if chosen is not None:
            return chosen
        choices = self.port_choices(cell_id).get(pin_id, ())
        return choices[0][0] if len(choices) == 1 else None

    def choice(self, cell_id: str, pin_id: str) -> Choice | None:
        """The pin's port in use: the one its wire took, else its first allowed port."""
        choices = self.port_choices(cell_id).get(pin_id, ())
        if not choices:
            return None
        chosen = self.routed_port(cell_id, pin_id)
        return next((c for c in choices if c[0] == chosen), choices[0])

    def attach_cells(self, cell_id: str) -> dict[str, XY]:
        """Every pin's attach cell for a placed cell, through the port in use."""
        out: dict[str, XY] = {}
        for pin_id in self.port_choices(cell_id):
            found = self.choice(cell_id, pin_id)
            if found is not None:
                out[pin_id] = found[1]
        return out

    def port_cells(self, cell_id: str) -> dict[str, XY]:
        """Every pin's port cell for a placed cell: the footprint cell its attach cell faces."""
        out: dict[str, XY] = {}
        for pin_id in self.port_choices(cell_id):
            found = self.choice(cell_id, pin_id)
            if found is not None:
                out[pin_id] = found[2]
        return out

    def open_ports(self, cell_id: str, pin_id: str) -> tuple[tuple[str, XY], ...]:
        """The ports the pin may still take with their attach cells: in the grid and not in use by another routed pin of the cell."""
        choices = self.port_choices(cell_id)
        taken = {
            self.routed_port(cell_id, other) for other in choices if other != pin_id
        }
        return tuple(
            (port_id, attach)
            for port_id, attach, _ in choices.get(pin_id, ())
            if port_id not in taken and self.in_grid(attach)
        )

    def attach_cell(self, cell_id: str, pin_id: str) -> XY | None:
        found = self.choice(cell_id, pin_id)
        return None if found is None else found[1]

    def nets_of(self, cell_id: str) -> tuple[Net, ...]:
        """The nets with a pin on the cell; built once per world."""
        table = self._nets_by_cell
        if table is None:
            table = {}
            for net in self.netlist.nets.values():
                for ref in net.pins():
                    table.setdefault(ref.cell, [])
                    if net not in table[ref.cell]:
                        table[ref.cell].append(net)
            self._nets_by_cell = table
        return tuple(table.get(cell_id, ()))

    def ready(self, net: Net) -> bool:
        """Whether the net can be routed now: a placed source (or the outside) and a placed sink; the rest of its pins join as they land."""
        fed = net.outside is not None or any(
            r.cell in self.placements for r in net.sources
        )
        return fed and any(r.cell in self.placements for r in net.sinks)

    def ready_nets(self, cell_id: str) -> tuple[Net, ...]:
        return tuple(
            n for n in self.nets_of(cell_id) if self.ready(n) and n.id not in self.wires
        )

    def grown_nets(self, cell_id: str) -> tuple[Net, ...]:
        """The routed nets of a cell, whose wires predate the cell's pins and must be grown to reach them."""
        return tuple(n for n in self.nets_of(cell_id) if n.id in self.wires)

    def unrouted(self) -> tuple[Net, ...]:
        return tuple(n for n in self.netlist.nets.values() if n.id not in self.wires)

    # ------------------------------------------------------------- tables
    def tables(self) -> "Tables":
        """The attach-cell tables of every placed pin, rebuilt after a placement changes and patched per net when a wire does."""
        if self._tables is not None:
            return self._tables
        tables = Tables()
        for net in self.netlist.nets.values():
            layer = self.carrier_layer(net.carrier)
            for ref in net.pins():
                for port_id, attach, _ in self.port_choices(ref.cell).get(ref.pin, ()):
                    tables.alternatives.setdefault(layer, {}).setdefault(
                        attach, []
                    ).append((ref.cell, ref.pin))
                if ref.cell in self.placements:
                    tables.pins.setdefault(net.id, []).append(
                        (ref.cell, ref.pin, layer)
                    )
        self._tables = tables
        for net_id in tables.pins:
            self.retable(net_id)
        return tables

    def untable(self) -> None:
        """Drop the tables; the next reader rebuilds them from the placements."""
        self._tables = None

    def table_cell(self, cell_id: str) -> None:
        """Write a newly placed cell's pins into the tables, its nets patched after."""
        tables = self._tables
        if tables is None:
            return
        touched: list[str] = []
        for net in self.nets_of(cell_id):
            layer = self.carrier_layer(net.carrier)
            for ref in net.pins():
                if ref.cell != cell_id:
                    continue
                for _, attach, _ in self.port_choices(cell_id).get(ref.pin, ()):
                    tables.alternatives.setdefault(layer, {}).setdefault(
                        attach, []
                    ).append((cell_id, ref.pin))
                tables.pins.setdefault(net.id, []).append((cell_id, ref.pin, layer))
            touched.append(net.id)
        for net_id in touched:
            self.retable(net_id)

    def untable_cell(self, cell_id: str) -> None:
        """Take a cell's pins out of the tables while its placement still stands, its nets patched after."""
        tables = self._tables
        if tables is None:
            return
        touched: list[str] = []
        for net in self.nets_of(cell_id):
            layer = self.carrier_layer(net.carrier)
            for ref in net.pins():
                if ref.cell != cell_id:
                    continue
                per_layer = tables.alternatives.get(layer, {})
                for _, attach, _ in self.port_choices(cell_id).get(ref.pin, ()):
                    owners = per_layer.get(attach)
                    if owners is not None:
                        owners[:] = [o for o in owners if o != (cell_id, ref.pin)]
                        if not owners:
                            per_layer.pop(attach, None)
            pins = tables.pins.get(net.id)
            if pins is not None:
                pins[:] = [entry for entry in pins if entry[0] != cell_id]
                if not pins:
                    tables.pins.pop(net.id, None)
            touched.append(net.id)
        for net_id in touched:
            self.retable(net_id)

    def retable(self, net_id: str) -> None:
        """Write the net's placed pins into the tables again, after its wire came or went."""
        tables = self._tables
        if tables is None:
            return
        for kind, layer, cell in tables.entries.pop(net_id, ()):
            table = getattr(tables, kind).get(layer, {})
            if kind == "ports" or table.get(cell) == net_id:
                table.pop(cell, None)
        written: list[tuple[str, str, XY]] = []
        wire = self.wires.get(net_id)
        held = wire.cells() if wire is not None else frozenset()
        for cell_id, pin_id, layer in tables.pins.get(net_id, ()):
            choices = self.port_choices(cell_id).get(pin_id, ())
            found = self.choice(cell_id, pin_id)
            if not choices or found is None:
                continue
            if wire is not None and found[1] in held:
                tables.routed.setdefault(layer, {})[found[1]] = net_id
                tables.ports.setdefault(layer, {})[found[1]] = found[2]
                written += [("routed", layer, found[1]), ("ports", layer, found[1])]
            elif len(choices) == 1:
                tables.open.setdefault(layer, {})[found[1]] = net_id
                written.append(("open", layer, found[1]))
        tables.entries[net_id] = written

    def open_attach_owners(self) -> dict[str, dict[XY, str]]:
        """Per layer, the net owning the only attach cell of a placed pin its wire does not hold (the net unrouted, or the pin not reached); a pin with a choice of ports reserves none."""
        return self.tables().open

    def routed_attach_owners(self) -> dict[str, dict[XY, str]]:
        """Per layer, the net whose wire uses each attach cell of a routed pin."""
        return self.tables().routed

    def routed_attach_ports(self) -> dict[str, dict[XY, XY]]:
        """Per layer, the port cell behind each attach cell a routed pin's wire uses."""
        return self.tables().ports


class Tables:
    """The attach cells of the placed pins: reserved while open, in use once routed, and every alternative."""

    def __init__(self) -> None:
        self.open: dict[str, dict[XY, str]] = {}
        self.routed: dict[str, dict[XY, str]] = {}
        self.ports: dict[str, dict[XY, XY]] = {}
        self.alternatives: dict[str, dict[XY, list[tuple[str, str]]]] = {}
        self.pins: dict[str, list[tuple[str, str, str]]] = {}
        self.entries: dict[str, list[tuple[str, str, XY]]] = {}


__all__ = ["AttachMixin", "Choice", "Tables", "options_at"]
