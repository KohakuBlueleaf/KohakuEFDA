"""IndustrialPlanner blueprint import: tiles, rotations, recipes, links, and the check command."""

import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.data.importers.industrial_planner import (
    import_industrial_planner,
    match_recipe,
    match_source_item,
)
from kohakuefda.flow.evaluate import evaluate
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Link
from kohakuefda.verify.rules.geometry import check_layout

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
FIXTURE = ROOT / "tests" / "fixtures" / "industrial_planner_min.json"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def test_import_geometry_and_config(dataset: Dataset) -> None:
    layout = import_industrial_planner(dataset, FIXTURE)
    by_id = {m.id: m for m in layout.machines}
    assert len(layout.machines) == 13 - 2
    assert (by_id["unl"].x, by_id["unl"].y, by_id["unl"].rotation) == (1, 5, 0)
    assert by_id["unl"].config == {"item": "item_xiranite_powder"}
    assert by_id["oven"].rotation == 180
    assert by_id["pool"].rotation == 0
    assert [s.cells for s in layout.segments] == [[(2, 6), (2, 7)]]
    assert layout.links == [Link(inlet="inlet", outlet="outlet")]
    assert layout.basement.basement_id == "sky_king_flats"
    assert layout.width >= 28 and layout.height >= 17


def test_import_matches_recipes_and_pump_fluid(dataset: Dataset) -> None:
    layout = import_industrial_planner(dataset, FIXTURE)
    by_id = {m.id: m for m in layout.machines}
    assert by_id["oven"].recipe_id == "xiranite_oven_xiranite_enr_powder_1"
    assert by_id["oven"].mode == "liquid"
    assert by_id["pool"].recipe_id == "pool_liquid_liquid_xiranite_1"
    assert by_id["pool2"].recipe_id == "pool_liquid_xiranite_poly_1"
    assert by_id["pump"].config == {"item": "item_liquid_water"}
    assert by_id["stash"].recipe_id is None
    assert (
        match_recipe(dataset, "mix_pool_1", "mix_pool_1", "r_nothing_like_it") is None
    )
    assert (
        match_source_item(dataset, "gas_pump_1", "r_gas_pump_gas_water_basic")
        == "item_gas_water"
    )


def test_imported_line_passes_drc_and_flows(dataset: Dataset) -> None:
    layout = import_industrial_planner(dataset, FIXTURE)
    assert [f for f in check_layout(dataset, layout) if f.severity == "error"] == []
    result = evaluate(dataset, layout)
    assert result.segments["belt0"].items == {"item_xiranite_powder": Fraction(30)}
    assert result.machines["ld"].inputs == {"item_xiranite_powder": Fraction(30)}


def test_check_command_detects_blueprints() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "kohakuefda", "check", str(FIXTURE), "--no-rates"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 errors" in proc.stdout
