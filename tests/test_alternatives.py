"""Alternative plans and bannable machines: a product with rival recipes yields another
feasible plan, a banned machine never appears, and the bannable list keeps the targets feasible.
"""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.model.basement import Region
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import BasementRef, PlanMode, Scenario
from kohakuefda.plan.alternatives import alternatives, bannable, used_recipes
from kohakuefda.plan.planner import plan

DATASET = (
    Path(__file__).resolve().parents[1] / "data" / "1.5.3@9764758-3" / "dataset.json"
)
WULING = BasementRef(
    region=Region.WULING, basement_id="sky_king_flats", level=3, depot_level=1
)
HETONITE = "item_copper_enr"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


@pytest.fixture(scope="module")
def hetonite(dataset: Dataset):
    scenario = Scenario(
        targets={HETONITE: Fraction(6)},
        basement=WULING,
        mode=PlanMode.MACHINES,
        gas=True,
        gas_default="plenty",
    )
    return scenario, plan(dataset, scenario)


def test_rival_recipes_give_other_feasible_plans(dataset: Dataset, hetonite) -> None:
    scenario, result = hetonite
    assert result.status == "ok"
    found = alternatives(dataset, scenario, result)
    assert found, "Hetonite has a crucible route and a gas route"
    seen = {frozenset(a.recipes) for a in found}
    assert len(seen) == len(found)
    for alternative in found:
        assert alternative.status in ("ok", "degraded")
        assert frozenset(alternative.recipes) != frozenset(used_recipes(result))
        assert alternative.recipe_id in alternative.recipes
        assert (
            alternative.scenario.recipe_overrides[alternative.item_id]
            == alternative.recipe_id
        )
    assert found == sorted(
        found, key=lambda a: (a.status != "ok", a.machine_count, a.footprint_cells)
    )


def test_banned_machines_never_appear_and_bannable_keeps_feasibility(
    dataset: Dataset, hetonite
) -> None:
    scenario, result = hetonite
    machines = bannable(dataset, scenario, result)
    assert machines
    assert not any(m in dataset.dumps for m in machines)
    for machine_id in machines:
        banned = scenario.model_copy(update={"banned_machines": [machine_id]})
        other = plan(dataset, banned)
        assert other.status != "infeasible"
        assert all(u.machine_id != machine_id for u in other.recipes)
    everything = scenario.model_copy(
        update={"banned_machines": sorted({u.machine_id for u in result.recipes})}
    )
    assert plan(dataset, everything).status == "infeasible"
