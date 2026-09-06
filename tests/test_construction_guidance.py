"""Outside routing stays physical but does not enlarge occupied build bounds."""

from pathlib import Path

import pytest

from kohakuefda.framework import problem_of
from kohakuefda.framework.assessment import metrics_of
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout, Segment
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["python"] + (["native"] if NATIVE else [])


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")


def problem_for(dataset, name):
    scenario = Scenario.from_toml(ROOT / f"tests/fixtures/scenario_{name}.toml")
    planned = plan(dataset, scenario)
    return problem_of(dataset, build_netlist(dataset, scenario, planned), planned)


@pytest.mark.parametrize("backend", BACKENDS)
def test_external_pipe_detours_do_not_inflate_live_or_materialized_area(
    dataset, backend
):
    runner = Runner(
        problem_for(dataset, "basic"),
        settings={"backend": backend, "check_rates": False},
    )
    site = runner.backend.site
    x0, y0, _, _ = site.area
    wire = next(w for w in site.wires if w.kind == "pipe")
    inside = [(x0 + 3, y) for y in range(y0, y0 + 4)]
    found = []
    for start in (x0 - 1, x0 - 5):
        cells = [(x, y0 - 1) for x in range(start, x0 + 4)] + inside
        if wire.cells:
            site.grid.remove_wire(1, wire.id, wire.cells)
        wire.cells = cells
        site.grid.add_wire(1, wire.id, cells, (start - 1, y0 - 1), (x0 + 3, y0 + 4))
        layout = Layout(
            dataset_version=dataset.version.id,
            basement=site.netlist.scenario.basement,
            width=site.width,
            height=site.height,
            area=site.area,
            segments=[Segment(id=wire.id, kind="pipe", cells=cells)],
        )
        found.append(metrics_of(site, layout, []))
        assert site.bbox() == (x0 + 3, y0, x0 + 4, y0 + 4)
        assert set(cells) <= site.occupied()
        assert tuple(runner.backend.frame("build")["rect"]) == site.bbox()
    for key in ("area", "width", "height", "waste", "occupied_cells"):
        assert found[0][key] == found[1][key]
    assert found[0]["area"] == 4
    assert found[1]["length"] > found[0]["length"]
