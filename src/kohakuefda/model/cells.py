"""Cells (one machine each), their pins, the groups the game's adjacency rules bind them
into, and the netlist that joins them."""

import json
from pathlib import Path
from typing import Literal

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.geometry import Edge
from kohakuefda.model.layout import Cell, Placed
from kohakuefda.model.plan import Finding
from kohakuefda.model.rates import Rate
from kohakuefda.model.scenario import Scenario

PinDirection = Literal["in", "out"]
LaneKind = Literal["belt", "pipe"]
CellKind = Literal[
    "recipe",
    "dump",
    "unloader",
    "loader",
    "entry",
    "zone",
    "depot",
    "core",
    "pylon",
]
Constraint = Literal["free", "edge", "slot", "park"]
BUS_GROUP = "bus"


class PortRef(EfdaModel):
    """A machine port a lane may use: its index, its cell in the cell's frame, and its edge."""

    index: int
    cell: Cell
    edge: Edge


class Pin(EfdaModel):
    """One lane of one item crossing the cell boundary.

    ``cell`` and ``edge`` are the default port; ``alternatives`` lists every port the lane may
    use instead, and placement picks one that no other lane of the cell has taken.
    """

    id: str
    direction: PinDirection
    kind: LaneKind
    item_id: str
    rate: Rate
    cell: Cell
    edge: Edge
    alternatives: list[PortRef] = []


class Fragment(EfdaModel):
    """Placed machines in local coordinates inside a width×height box."""

    width: int
    height: int
    machines: list[Placed] = []

    @property
    def area(self) -> int:
        return self.width * self.height


class CellInstance(Fragment):
    """A cell: one machine at the origin plus its pins and what it runs.

    ``env`` is the environment a recipe cell needs or a zone cell creates; ``group`` names the
    cluster the game binds the cell into (``bus`` for Depot Bus parts and bricks, ``zone<n>``
    for a Gas Dispersing Unit and its machines); ``constraint`` says where placement may put
    it: anywhere inside the Core AIC Area (``free``), on a border cell of the area (``edge``,
    an outside input), on one of the fixed Depot Bus slots (``slot``, Valley IV bricks), or
    anywhere out of the way (``park``, the unused Automation-Core).
    """

    id: str
    kind: CellKind
    machine_id: str
    recipe_id: str | None = None
    pins: list[Pin] = []
    env: str | None = None
    group: str | None = None
    constraint: Constraint = "free"

    def pins_of(self, direction: PinDirection) -> list[Pin]:
        return [p for p in self.pins if p.direction == direction]

    def pin(self, pin_id: str) -> Pin:
        return next(p for p in self.pins if p.id == pin_id)


class PinRef(EfdaModel):
    """A pin of a cell taking part in a net, with the rate it carries at steady state."""

    cell_id: str
    pin_id: str
    rate: Rate


class NetSpec(EfdaModel):
    """One item's flow between pins: planned rate, nominal lane capacity, trunk lanes."""

    id: str
    item_id: str
    kind: LaneKind
    rate: Rate
    nominal: Rate
    trunk_lanes: int
    sources: list[PinRef] = []
    sinks: list[PinRef] = []
    via_depot_ok: bool = False


class Netlist(EfdaModel):
    """Cells and nets for a scenario; the input of the layout stage."""

    schema_version: int = 3
    dataset_version: str
    scenario: Scenario
    plan_status: str
    cells: list[CellInstance] = []
    nets: list[NetSpec] = []
    findings: list[Finding] = []

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=1) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Netlist":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def cell(self, cell_id: str) -> CellInstance:
        return next(c for c in self.cells if c.id == cell_id)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]
