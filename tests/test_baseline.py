"""First-feasible spread and greedy shrink on the Hub battery regression."""

from pathlib import Path

import pytest

from kohakuefda.framework import problem_of, solve
from kohakuefda.layout.board import board_of
from kohakuefda.layout.engine import Engine
from kohakuefda.layout.stages import netlist_stage, params_of, plan_stage
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.solvers.baseline import Baseline
from kohakuefda.verify.rules.geometry import check_layout

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def battery():
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_hub_battery.toml")
    plan = plan_stage(dataset, scenario)
    assert plan.status == "ok" and plan.targets[0].achieved == 6
    netlist = netlist_stage(dataset, scenario, plan)
    assert len(netlist.cells) == 43 and not netlist.errors
    return dataset, netlist


def test_hub_battery_stops_at_first_complete_spread_and_shrinks(battery) -> None:
    dataset, netlist = battery
    settings = params_of("layout", {"workers": 1, "spread_attempts": 32})
    engine = Engine(dataset, netlist, board_of(dataset, netlist.scenario), settings)
    result = engine.run()
    assert 1 <= engine.spread.tried < settings["spread_attempts"]
    assert not engine.site.unplaced() and not engine.site.unrouted()
    assert result.fits and not [f for f in result.findings if f.severity == "error"]
    assert not [
        f for f in check_layout(dataset, result.layout) if f.severity == "error"
    ]
    expected = {machine.id for cell in netlist.cells for machine in cell.machines}
    assert expected <= {machine.id for machine in result.layout.machines}
    assert result.terms["area"] < 64 * 64


def test_spread_exhaustion_keeps_an_honest_incomplete_result(battery) -> None:
    dataset, netlist = battery
    solver = Baseline(spread_attempts=1, spread_gap=6)
    result = solve(problem_of(dataset, netlist), solver)
    assert result.status == "no_solution_found"
    assert solver.spread.tried == 1
    assert result.current is not None and not result.current.assessment.complete
    assert result.best_routed is None
    assert any(i.rule == "layout.unplaced" for i in result.current.assessment.issues)
