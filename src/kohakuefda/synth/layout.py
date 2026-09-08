"""A framework layout back into the project's ``Placement`` and ``Layout``.

Placements become the cells' machines at their anchors; field units become pylons;
junction and bridge units become logistics units with the rotation the flow gives them;
each wire becomes segments cut at its units, oriented from source to sink, with the entry
and heading the connectivity rules read; outside inputs become entries.
"""

from fractions import Fraction
from typing import Any

from kohakuefda.layout.fragments import rotate, translate
from kohakuefda.model.cells import CellInstance
from kohakuefda.model.cells import Netlist as ProjectNetlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge, edge_step, rotate_edge
from kohakuefda.model.layout import Cell as XY
from kohakuefda.model.layout import Entry, Layout, Placed, Segment, Unit
from kohakuefda.model.placement import PlacedBlock, Placement
from kohakuefda.model.plan import Finding
from kohakuefda.physics.boundaries import OPPOSITE, rect_of
from kohakuefda.physics.fabric import area_rect
from kohakuefda.physics.facts import facts, pin_facts
from kohakuefda.physics.library import (
    CONVERGER,
    PYLON,
    SPLITTER,
    UNIT_CARRIER,
)
from kohakuefda.synth.flows import BRIDGES, CONVERGERS, SPLITTERS, Flows, step_between
from kohakuefda.synth.footprints import ENTRY
from kohakuefda.synth.problem import project_pin_id
from kohakulayout.ir import Layout as FrameworkLayout
from kohakulayout.ir import Problem
from kohakulayout.ir.geometry import attach_cell, rotate_side

SIDE_EDGE = {"N": Edge.N, "E": Edge.E, "S": Edge.S, "W": Edge.W}
HEADINGS = {(1, 0): Edge.E, (-1, 0): Edge.W, (0, 1): Edge.S, (0, -1): Edge.N}


def rotation_facing(edge: Edge, wanted: Edge) -> int:
    """The rotation turning a unit's ``edge`` port onto ``wanted``."""
    return next(r for r in (0, 90, 180, 270) if rotate_edge(edge, r) is wanted)


class Translation(Flows):
    """One framework layout read against its problem and the project netlist."""

    def __init__(
        self,
        problem: Problem,
        layout: FrameworkLayout,
        dataset: Dataset,
        netlist: ProjectNetlist,
    ) -> None:
        self.problem = problem
        self.layout = layout
        self.dataset = dataset
        self.netlist = netlist
        self.cells = {c.id: c for c in netlist.cells}
        self.kl = problem.netlist
        self.library = {**problem.netlist.library}
        self.attach: dict[tuple[str, str], XY] = {}
        for cell_id, placement in layout.placements.items():
            fp = self.library.get(self.kl.cells[cell_id].footprint or "")
            if fp is None:
                continue
            for pin in self.kl.cells[cell_id].pins:
                port = fp.port(pin.ports[0]) if pin.ports else None
                if port is None:
                    continue
                ax, ay = attach_cell(
                    fp.width, fp.height, port.side, port.offset, placement.rot
                )
                self.attach[(cell_id, pin.id)] = (placement.x + ax, placement.y + ay)
        self.sources = {
            xy
            for (cell_id, pin_id), xy in self.attach.items()
            if self._out(cell_id, pin_id)
        }
        self.units_of: dict[str, set[XY]] = {}
        self.bridges_of: dict[str, set[XY]] = {}
        for u in layout.units.values():
            if u.owner.startswith("field:"):
                continue
            carrier = UNIT_CARRIER.get(u.footprint, "")
            if u.footprint in BRIDGES:
                self.bridges_of.setdefault(carrier, set()).add((u.x, u.y))
            else:
                self.units_of.setdefault(u.owner.removeprefix("net:"), set()).add(
                    (u.x, u.y)
                )

    def footprint_of(self, cell_id: str) -> Any:
        return self.library.get(self.kl.cells[cell_id].footprint or "")

    def _out(self, cell_id: str, pin_id: str) -> bool:
        return any(
            p.id == pin_id and p.direction == "out" for p in self.kl.cells[cell_id].pins
        )

    # ------------------------------------------------------------ machines
    def machines(self) -> tuple[list[Placed], list[Entry]]:
        placed: list[Placed] = []
        entries: list[Entry] = []
        for cell_id, placement in self.layout.placements.items():
            cell = self.cells[cell_id]
            if cell.machine_id == ENTRY:
                entries.append(self.entry(cell, placement))
                continue
            fragment = (
                rotate(self.dataset, cell, placement.rot) if placement.rot else cell
            )
            placed.extend(translate(fragment, placement.x, placement.y).machines)
        for index, unit in enumerate(self.pylons()):
            placed.append(
                Placed(id=f"pylon{index}", machine_id=PYLON, x=unit.x, y=unit.y)
            )
        return placed, entries

    def pylons(self) -> list[Any]:
        return sorted(
            (u for u in self.layout.units.values() if u.owner == "field:power"),
            key=lambda u: (u.y, u.x),
        )

    def entry(self, cell: CellInstance, placement: Any) -> Entry:
        pin = cell.pins[0]
        facing = rotate_side("E", placement.rot)
        return Entry(
            id=cell.id,
            item_id=pin.item_id,
            rate=pin.rate,
            x=placement.x,
            y=placement.y,
            edge=SIDE_EDGE[OPPOSITE[facing]],
        )

    def units(self) -> list[Unit]:
        """Bridges as they are; each junction, placed or met at a terminal, as the splitter or converger its flows ask for."""
        out: list[Unit] = []
        for unit_id, unit in sorted(self.layout.units.items()):
            if unit.owner.startswith("field:") or unit.footprint not in BRIDGES:
                continue
            out.append(Unit(id=unit_id, unit_id=unit.footprint, x=unit.x, y=unit.y))
        placed = {
            (u.x, u.y): unit_id
            for unit_id, u in self.layout.units.items()
            if u.owner.startswith("net:") and u.footprint not in BRIDGES
        }
        for net_id, net in self.kl.nets.items():
            for xy in sorted(self.junction_cells(net_id)):
                kind, came, goes = self.junction(net_id, xy)
                if kind is None:
                    continue
                rotation = 0
                if kind == "split" and came is not None:
                    rotation = rotation_facing(Edge.N, OPPOSITE_EDGE[HEADINGS[came]])
                elif kind == "merge" and goes is not None:
                    rotation = rotation_facing(Edge.S, HEADINGS[goes])
                table = SPLITTER if kind == "split" else CONVERGER
                unit_id = placed.get(xy, f"j_{net_id}_{xy[0]}_{xy[1]}")
                out.append(
                    Unit(
                        id=unit_id,
                        unit_id=table[net.carrier],
                        x=xy[0],
                        y=xy[1],
                        rotation=rotation,
                    )
                )
        return out

    def segments(self) -> list[Segment]:
        out: list[Segment] = []
        for net_id, net in self.kl.nets.items():
            if net_id not in self.layout.wires:
                continue
            item_id = facts(net).get("item")
            graph = self.graph(net_id)
            flows = self.flows(net_id)
            for index, piece in enumerate(self.oriented(net_id)):
                out.append(
                    Segment(
                        id=f"{net_id}.p{index}",
                        kind=net.carrier,
                        cells=list(piece),
                        entry=self.entry_of(piece, graph, flows),
                        heading=self.heading_of(piece, graph, flows),
                        item_id=item_id,
                    )
                )
        return out

    @staticmethod
    def pieces(cells: list[XY], cuts: set[XY]) -> list[list[XY]]:
        out: list[list[XY]] = []
        current: list[XY] = []
        for cell in cells:
            if cell in cuts:
                if current:
                    out.append(current)
                current = []
            else:
                current.append(cell)
        if current:
            out.append(current)
        return out

    def entry_of(
        self,
        piece: list[XY],
        graph: dict[XY, set[XY]],
        flows: dict[tuple[XY, XY], Fraction],
    ) -> Edge | None:
        """The travel into the first cell: from the unit the flow comes from, else out of the port it starts at."""
        first = piece[0]
        inner = piece[1] if len(piece) > 1 else None
        behind = [
            c
            for c in graph.get(first, ())
            if c != inner and flows.get((c, first), 0) > 0
        ]
        if not behind and not flows:
            behind = [c for c in graph.get(first, ()) if c != inner]
        if behind:
            return HEADINGS[step_between(behind[0], first)]
        port = self.port_at(first, "out")
        return None if port is None else HEADINGS[port]

    def heading_of(
        self,
        piece: list[XY],
        graph: dict[XY, set[XY]],
        flows: dict[tuple[XY, XY], Fraction],
    ) -> Edge | None:
        """The travel out of the last cell: to the unit the flow goes on to, else into the port it ends at."""
        last = piece[-1]
        inner = piece[-2] if len(piece) > 1 else None
        ahead = [
            c for c in graph.get(last, ()) if c != inner and flows.get((last, c), 0) > 0
        ]
        if not ahead and not flows:
            ahead = [c for c in graph.get(last, ()) if c != inner]
        if ahead:
            return HEADINGS[step_between(last, ahead[0])]
        port = self.port_at(last, "in")
        return None if port is None else HEADINGS[port]

    def port_at(self, xy: XY, direction: str) -> tuple[int, int] | None:
        """The outward step of the port whose attach cell is ``xy``, as the flow crosses it."""
        for (cell_id, pin_id), attach in self.attach.items():
            if attach != xy or (self._out(cell_id, pin_id) != (direction == "out")):
                continue
            placement = self.layout.placements[cell_id]
            fp = self.library[self.kl.cells[cell_id].footprint or ""]
            pin = next(p for p in self.kl.cells[cell_id].pins if p.id == pin_id)
            port = fp.port(pin.ports[0])
            side = rotate_side(port.side, placement.rot)
            dx, dy = edge_step(SIDE_EDGE[side])
            return (dx, dy) if direction == "out" else (-dx, -dy)
        return None

    # -------------------------------------------------------------- output
    def terms(self, metrics: dict[str, Any]) -> dict[str, float]:
        """The framework metrics as the project's cost terms, with the legacy names the studio reads."""
        out = {
            k: float(v)
            for k, v in metrics.items()
            if isinstance(v, int | float | Fraction)
        }
        units = self.units()
        machine_cells = 0
        for cell_id, placement in self.layout.placements.items():
            x0, y0, x1, y1 = rect_of(self, cell_id, placement)
            machine_cells += (x1 - x0) * (y1 - y0)
        out["width"] = float(metrics.get("extent_w", 0))
        out["height"] = float(metrics.get("extent_h", 0))
        out["length"] = float(metrics.get("wire_cells", 0))
        out["pylons"] = float(len(self.pylons()))
        out["junctions"] = float(
            sum(1 for u in units if u.unit_id in SPLITTERS or u.unit_id in CONVERGERS)
        )
        out["waste"] = max(0.0, out.get("area", 0.0) - machine_cells - out["length"])
        return out

    def placement(self, metrics: dict[str, Any], findings: list[Finding]) -> Placement:
        blocks: list[PlacedBlock] = []
        for cell_id, placement in self.layout.placements.items():
            cell = self.cells[cell_id]
            blocks.append(
                PlacedBlock(
                    id=cell_id,
                    x=placement.x,
                    y=placement.y,
                    rotation=placement.rot,
                    width=cell.width,
                    height=cell.height,
                    ports=dict.fromkeys((p.id for p in cell.pins), 0),
                )
            )
        square = tuple(self.problem.params["square"])
        x0, y0, x1, y1 = area_rect(self.problem.fabric)
        _, entries = self.machines()
        return Placement(
            dataset_version=self.netlist.dataset_version,
            square=(int(square[0]), int(square[1])),
            grid=(self.problem.fabric.width, self.problem.fabric.height),
            area=(x0, y0, x1, y1),
            gap=0,
            cost=float(metrics.get("area", 0)),
            terms=self.terms(metrics),
            blocks=blocks,
            pylons=[(u.x, u.y) for u in self.pylons()],
            entries=entries,
            findings=findings,
        )

    def project_layout(self) -> Layout:
        machines, entries = self.machines()
        x0, y0, x1, y1 = area_rect(self.problem.fabric)
        return Layout(
            dataset_version=self.netlist.dataset_version,
            basement=self.netlist.scenario.basement,
            width=self.problem.fabric.width,
            height=self.problem.fabric.height,
            area=(x0, y0, x1, y1),
            machines=machines,
            units=self.units(),
            segments=self.segments(),
            entries=entries,
        )


OPPOSITE_EDGE = {Edge.N: Edge.S, Edge.S: Edge.N, Edge.E: Edge.W, Edge.W: Edge.E}


def findings_of(assessment: Any) -> list[Finding]:
    return [
        Finding(rule=f.rule, severity=f.severity, subject=f.subject, message=f.message)
        for f in getattr(assessment, "findings", ())
    ]


def layout_of(
    problem: Problem,
    layout: FrameworkLayout,
    dataset: Dataset,
    netlist: ProjectNetlist,
    assessment: Any = None,
) -> tuple[Placement, Layout]:
    """The project's placement checkpoint and layout for a framework layout of ``problem``."""
    translation = Translation(problem, layout, dataset, netlist)
    metrics = dict(getattr(assessment, "metrics", {}) or {})
    findings = findings_of(assessment) if assessment is not None else []
    return translation.placement(metrics, findings), translation.project_layout()


def pin_rate(cell: Any, pin_id: str) -> Fraction:
    found = pin_facts(cell).get(pin_id)
    return found[1] if found else Fraction(0)


__all__ = ["Translation", "findings_of", "layout_of", "pin_rate", "project_pin_id"]
