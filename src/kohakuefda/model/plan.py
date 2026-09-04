"""The plan: what the logical planner decided for a scenario."""

import json
from pathlib import Path
from typing import Literal

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.rates import Rate
from kohakuefda.model.scenario import Scenario, TargetGoal

Severity = Literal["info", "warning", "error"]
Status = Literal["ok", "degraded", "infeasible"]


class RecipeUse(EfdaModel):
    """A recipe running at ``crafts_per_min`` on ``machines`` machines."""

    recipe_id: str
    machine_id: str
    mode: str
    crafts_per_min: Rate
    machines_exact: Rate
    machines: int


class ItemBalance(EfdaModel):
    """Per-item steady-state flows in units per minute."""

    item_id: str
    produced: Rate
    consumed: Rate
    supplied: Rate
    delivered: Rate
    sunk: Rate
    sink_kind: str | None = None
    net: Rate


class Net(EfdaModel):
    """A flow of one item from a source to a consumer, and the lanes it needs."""

    item_id: str
    source: str
    target: str
    rate: Rate
    fluid: bool
    lanes: int
    lane_capacity: Rate


class TargetResult(EfdaModel):
    """A target with its resolved request; ``goal`` names a rate-free intent (``min``, ``max``)."""

    item_id: str
    requested: Rate
    achieved: Rate
    goal: TargetGoal | None = None


class Finding(EfdaModel):
    """A rule result: id, severity, the subject it points at, and a message."""

    rule: str
    severity: Severity
    subject: str
    message: str


class Cell(EfdaModel):
    """Identical machines running one recipe, with per-machine rates."""

    recipe_id: str
    machine_id: str
    mode: str
    count: int
    inputs: dict[str, Rate]
    outputs: dict[str, Rate]


class Plan(EfdaModel):
    """Recipes, machine counts, balances, nets, cells, zones and findings for a scenario.

    ``power`` is the total the machines draw (game-knowledge PWR-05); ``zones`` counts the Gas
    Dispersing Units per environment (ENV-01).
    """

    schema_version: int = 3
    dataset_version: str
    scenario: Scenario
    status: Status
    scale: Rate
    targets: list[TargetResult]
    recipes: list[RecipeUse]
    items: dict[str, ItemBalance]
    nets: list[Net]
    cells: list[Cell]
    findings: list[Finding]
    power: int
    footprint_cells: int
    machine_count: int
    zones: dict[str, int] = {}

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=1) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Plan":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]
