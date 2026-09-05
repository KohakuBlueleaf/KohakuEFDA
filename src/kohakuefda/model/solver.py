"""Immutable values exchanged by layout solvers and the execution framework."""

from dataclasses import dataclass
from typing import Literal

Anchor = tuple[int, int, int]
Cell = tuple[int, int]
Rect = tuple[int, int, int, int]
Verdict = Literal["pass", "fail", "not_checked"]


@dataclass(frozen=True)
class Problem:
    """An immutable, portable problem with exact serialized domain inputs."""

    id: str
    dataset_json: str
    netlist_json: str
    plan_json: str | None = None
    rules: str = "endfield-ports-v1"


@dataclass(frozen=True)
class PortChoice:
    """A compatible physical endpoint, not a mandatory default."""

    index: int
    cell: Cell
    edge: str


@dataclass(frozen=True)
class Lane:
    id: str
    direction: str
    kind: str
    item_id: str
    rate: str
    choices: tuple[PortChoice, ...]


@dataclass(frozen=True)
class BlockInfo:
    id: str
    machine_id: str
    kind: str
    constraint: str
    group: str | None
    width: int
    height: int
    lanes: tuple[Lane, ...]
    footprints: tuple[tuple[Cell, ...], ...]
    ports: tuple[tuple[Cell, ...], ...]


@dataclass(frozen=True)
class Link:
    id: str
    source: str
    sink: str
    kind: str
    rate: str


@dataclass(frozen=True)
class WorldView:
    """Read-only placement, routing and geometry queries at one revision."""

    revision: int
    area: Rect
    grid: tuple[int, int]
    anchors: tuple[tuple[str, Anchor], ...]
    footprints: tuple[tuple[str, tuple[Cell, ...]], ...]
    occupied: frozenset[Cell]
    bbox: Rect
    missing: tuple[str, ...]
    unrouted: tuple[str, ...]
    wire_cells: int


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: str
    subject: str
    message: str


@dataclass(frozen=True)
class Assessment:
    complete: bool
    geometry: Verdict
    routing: Verdict
    rates: Verdict
    issues: tuple[Issue, ...]
    metrics: tuple[tuple[str, float], ...]

    @property
    def routed(self) -> bool:
        return self.complete and self.geometry == "pass" and self.routing == "pass"

    @property
    def verified(self) -> bool:
        return self.routed and self.rates == "pass"


@dataclass(frozen=True)
class Snapshot:
    """Concrete layout plus routing state; JSON strings prevent mutable aliases."""

    problem_id: str
    id: str
    backend: str
    payload: str
    layout_json: str
    placement_json: str
    assessment: Assessment


@dataclass(frozen=True)
class Scope:
    """Entities an action may change; None routes permits any affected route."""

    machines: frozenset[str]
    routes: frozenset[str] | None = None
    support: bool = True


@dataclass(frozen=True)
class Action:
    """An edit intent; handlers execute only inside a private transaction."""

    name: str
    anchors: tuple[tuple[str, Anchor], ...] = ()
    order: tuple[str, ...] = ()
    routes: tuple[str, ...] = ()
    scope: Scope | None = None
    options: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Candidate:
    session: str
    base_revision: int
    snapshot: Snapshot


@dataclass(frozen=True)
class AttemptResult:
    status: str
    candidate: Candidate | None = None
    message: str = ""
    required_routes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SolveEvent:
    sequence: int
    kind: str
    elapsed: float
    duration: float
    revision: int
    payload_json: str


@dataclass(frozen=True)
class SolveResult:
    status: str
    current: Snapshot | None
    best_routed: Snapshot | None
    best_verified: Snapshot | None
    elapsed: float
    work: tuple[tuple[str, int], ...]
    settings_json: str
    error: str = ""
