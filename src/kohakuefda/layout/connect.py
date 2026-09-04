"""Connectivity of a layout: which port each segment leaves from and arrives at.

A segment starts on the cell an OUT port faces and ends on the cell an IN port faces. When
several ports face the same cell, the one in line with the segment's direction of travel wins
(its recorded ``entry`` and ``heading``, else its first or last step), and a segment never
ends on the very port cell it came from. A single cell knows only where it leaves to (its heading), so its target
is fixed first and its source is any other port facing it: a turn between two units. A
logistics unit is itself a cell of the belt network, so a unit whose port faces another
entity's port across a shared edge connects to it directly, carried as a synthetic segment
without cells whose id starts with ``link:``; two **machines** standing edge to edge never
transfer, because a connection always costs a belt or pipe cell (game-knowledge LOG-11).
"""

from kohakuefda.layout.geometry import WorldPort, machine_ports, unit_ports
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge, edge_step
from kohakuefda.model.layout import Cell, Entry, Layout, Segment
from kohakuefda.model.machines import SKY, Port, PortDir, PortType

Step = tuple[int, int]
OPPOSITE = {Edge.N: Edge.S, Edge.S: Edge.N, Edge.E: Edge.W, Edge.W: Edge.E}


def entry_port(entry: Entry) -> WorldPort:
    """An outside input as an OUT pipe port on its border cell, facing inward."""
    port = Port(
        index=0,
        direction=PortDir.OUT,
        type=PortType.PIPE,
        x=entry.x,
        y=entry.y,
        edge=entry.inward,
        layer=SKY,
    )
    return WorldPort(entry.owner, port, entry.cell, entry.inward)


class Connection:
    """A segment with the OUT port it starts from and the IN port it ends at (either may be missing)."""

    def __init__(self, segment: Segment) -> None:
        self.segment = segment
        self.source: WorldPort | None = None
        self.target: WorldPort | None = None

    @property
    def direct(self) -> bool:
        return not self.segment.cells


def _step(a: Cell, b: Cell) -> Step:
    return (b[0] - a[0], b[1] - a[1])


def _prefer(ports: list[WorldPort], cell: Cell) -> list[WorldPort]:
    """Ports sitting on ``cell`` first; every port when none does."""
    good = [p for p in ports if p.cell == cell]
    return good or ports


class Connectivity:
    """All world ports of a layout and the connections of every segment and direct link."""

    def __init__(self, dataset: Dataset, layout: Layout) -> None:
        self.dataset = dataset
        self.layout = layout
        self.ports: list[WorldPort] = []
        self.unit_owners = {u.id for u in layout.units}
        for placed in layout.machines:
            self.ports.extend(machine_ports(dataset, placed))
        for unit in layout.units:
            self.ports.extend(unit_ports(dataset, unit))
        for entry in layout.entries:
            self.ports.append(entry_port(entry))
        self.by_outside: dict[tuple[Cell, str, str], list[WorldPort]] = {}
        self.by_cell: dict[tuple[Cell, str, str], list[WorldPort]] = {}
        for port in self.ports:
            self.by_outside.setdefault(
                (port.outside, port.direction, port.type), []
            ).append(port)
            self.by_cell.setdefault((port.cell, port.direction, port.type), []).append(
                port
            )
        self.segments: dict[str, Segment] = {s.id: s for s in layout.segments}
        self.connections: dict[str, Connection] = {}
        for segment in layout.segments:
            self.connections[segment.id] = self._connect(segment)
        for link in self._direct_links():
            self.segments[link.segment.id] = link.segment
            self.connections[link.segment.id] = link

    def _steps(self, segment: Segment) -> tuple[Step | None, Step | None]:
        """Travel direction into the first cell and out of the last: the recorded entry and
        heading when the segment carries them, else its first and last moves."""
        cells = segment.cells
        first = edge_step(segment.entry) if segment.entry is not None else None
        last = edge_step(segment.heading) if segment.heading is not None else None
        if len(cells) >= 2:
            first = first or _step(cells[0], cells[1])
            last = last or _step(cells[-2], cells[-1])
        else:
            first = first or last
            last = last or first
        return first, last

    def _connect(self, segment: Segment) -> Connection:
        port_type = PortType.PIPE if segment.kind == "pipe" else PortType.BELT
        conn = Connection(segment)
        if not segment.cells:
            return conn
        start, end = segment.start, segment.end
        first, last = self._steps(segment)
        sources = self.by_outside.get((start, PortDir.OUT, port_type), [])
        targets = self.by_outside.get((end, PortDir.IN, port_type), [])
        if first is not None:
            sources = _prefer(sources, (start[0] - first[0], start[1] - first[1]))
        if last is not None:
            targets = _prefer(targets, (end[0] + last[0], end[1] + last[1]))
        if len(segment.cells) == 1:
            conn.target = targets[0] if targets else None
            if conn.target is not None:
                goes_to = (conn.target.owner, conn.target.cell)
                sources = [
                    s for s in sources if (s.owner, s.cell) != goes_to
                ] or sources
            conn.source = sources[0] if sources else None
            return conn
        conn.source = sources[0] if sources else None
        if conn.source is not None:
            came_from = (conn.source.owner, conn.source.cell)
            targets = [t for t in targets if (t.owner, t.cell) != came_from]
        conn.target = targets[0] if targets else None
        return conn

    def _direct_links(self) -> list[Connection]:
        """OUT ports whose facing cell holds another entity's IN port facing back.

        At least one end must be a logistics unit: a splitter, converger or bridge is itself a
        cell of the belt network, so it feeds a machine port it touches, but two machines that
        merely stand edge to edge do not transfer — that needs a belt cell (LOG-11).
        """
        links: list[Connection] = []
        for port in self.ports:
            if port.direction != PortDir.OUT:
                continue
            facing = [
                t
                for t in self.by_cell.get((port.outside, PortDir.IN, port.type), [])
                if t.owner != port.owner
                and t.edge is OPPOSITE[port.edge]
                and (port.owner in self.unit_owners or t.owner in self.unit_owners)
            ]
            if not facing:
                continue
            kind = "pipe" if port.type == PortType.PIPE else "belt"
            segment = Segment(
                id=f"link:{port.owner}:{port.port.index}:{port.edge}",
                kind=kind,
                cells=[],
            )
            link = Connection(segment)
            link.source = port
            link.target = facing[0]
            links.append(link)
        return links

    def ports_of(self, owner: str) -> list[WorldPort]:
        return [p for p in self.ports if p.owner == owner]

    def outgoing(self, owner: str) -> list[Connection]:
        return [
            c for c in self.connections.values() if c.source and c.source.owner == owner
        ]

    def incoming(self, owner: str) -> list[Connection]:
        return [
            c for c in self.connections.values() if c.target and c.target.owner == owner
        ]
