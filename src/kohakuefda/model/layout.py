"""The layout: placed machines, logistics units, belt and pipe paths, conduit links."""

import json
from pathlib import Path
from typing import Literal

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.geometry import Edge, Rotation, edge_step, rotate_edge
from kohakuefda.model.rates import Rate
from kohakuefda.model.scenario import BasementRef

Cell = tuple[int, int]
SegmentKind = Literal["belt", "pipe"]


class Placed(EfdaModel):
    """A machine (or PAC, loader, conduit end, bus part) at an anchor cell with a rotation."""

    id: str
    machine_id: str
    x: int
    y: int
    rotation: Rotation = 0
    mode: str | None = None
    recipe_id: str | None = None
    config: dict[str, str] = {}


class Unit(EfdaModel):
    """A 1×1 logistics unit (splitter, converger, bridge, control port) with a rotation."""

    id: str
    unit_id: str
    x: int
    y: int
    rotation: Rotation = 0
    config: dict[str, str] = {}


class Segment(EfdaModel):
    """An ordered path of cells carrying one belt or one pipe, source first.

    ``entry`` is the direction of travel into the first cell and ``heading`` the direction
    of travel out of the last one; they name the port or unit the segment comes from and
    goes to when the path turns at its ends, and are the only direction a single cell has.
    ``item_id`` is what the planner routed on it, for reading the layout.
    """

    id: str
    kind: SegmentKind
    cells: list[Cell]
    heading: Edge | None = None
    entry: Edge | None = None
    item_id: str | None = None

    @property
    def start(self) -> Cell:
        return self.cells[0]

    @property
    def end(self) -> Cell:
        return self.cells[-1]


class Link(EfdaModel):
    """A conduit pair: the inlet and outlet placed ids."""

    inlet: str
    outlet: str


class Module(EfdaModel):
    """A blueprint-sized tile of the layout and the ids of the entities anchored in it."""

    id: str
    x: int
    y: int
    width: int
    height: int
    entities: list[str] = []


Rect = tuple[int, int, int, int]


class Entry(EfdaModel):
    """An outside input: a fluid arriving by pipe at a border cell of the area.

    The pipe's first cell is ``(x, y)``; ``edge`` is the side of the area it comes from, so
    the pump, extractor or conduit outside stands beyond that edge (game-knowledge RES-09).
    """

    id: str
    item_id: str
    rate: Rate
    x: int
    y: int
    edge: Edge

    @property
    def cell(self) -> Cell:
        return (self.x, self.y)

    @property
    def owner(self) -> str:
        """The entity name the entry's port carries in connectivity and occupancy."""
        return f"entry:{self.id}"

    @property
    def outside(self) -> Cell:
        """The cell beyond the edge, where the outside pipe stands."""
        dx, dy = edge_step(self.edge)
        return (self.x + dx, self.y + dy)

    @property
    def inward(self) -> Edge:
        return rotate_edge(self.edge, 180)

    @property
    def start(self) -> Cell:
        """The first cell of the pipe inside the area."""
        dx, dy = edge_step(self.inward)
        return (self.x + dx, self.y + dy)


class Layout(EfdaModel):
    """Everything placed in one basement, in grid cells (x right, y down, anchor top-left).

    ``area`` is the Core AIC Area inside the grid as ``(x0, y0, x1, y1)``; the cells around it
    are the ring where only pipes, pylons and a fixed Depot Bus may sit (game-knowledge
    REG-03). ``None`` means the whole grid is the area. ``entries`` are the outside inputs.
    """

    schema_version: int = 3
    dataset_version: str
    basement: BasementRef
    width: int
    height: int
    area: Rect | None = None
    machines: list[Placed] = []
    units: list[Unit] = []
    segments: list[Segment] = []
    links: list[Link] = []
    entries: list[Entry] = []
    modules: list[Module] = []
    notes: str = ""

    @property
    def area_rect(self) -> Rect:
        return self.area if self.area is not None else (0, 0, self.width, self.height)

    @property
    def origin(self) -> Cell:
        """The grid cell at the area's top-left corner (square coordinate ``(0, 0)``)."""
        return self.area_rect[0], self.area_rect[1]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=1) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Layout":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def machine(self, placed_id: str) -> Placed:
        return next(m for m in self.machines if m.id == placed_id)

    def belts(self) -> list[Segment]:
        return [s for s in self.segments if s.kind == "belt"]

    def pipes(self) -> list[Segment]:
        return [s for s in self.segments if s.kind == "pipe"]
