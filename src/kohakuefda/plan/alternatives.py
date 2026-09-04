"""Alternative plans: every other way the targets can be made when a recipe has rivals.

For each recipe the plan uses, every other allowed recipe for the same product is tried as an
override; the plans that come out feasible with a different recipe set are the alternatives,
ranked by machine count and footprint. A machine the player bans (``Scenario.banned_machines``)
never appears; ``bannable`` lists the machines whose ban still leaves a feasible plan.
"""

import logging

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Plan
from kohakuefda.model.rates import Rate
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.planner import DUMP_PREFIX, plan
from kohakuefda.plan.recipes import candidates

log = logging.getLogger(__name__)
LIMIT = 6


class Alternative(EfdaModel):
    """A feasible plan that uses a different recipe for one product, and how it compares."""

    item_id: str
    recipe_id: str
    machine_id: str
    scenario: Scenario
    status: str
    machine_count: int
    footprint_cells: int
    power: int
    scale: Rate
    recipes: list[str]


def used_recipes(result: Plan) -> set[str]:
    return {
        u.recipe_id for u in result.recipes if not u.recipe_id.startswith(DUMP_PREFIX)
    }


def alternatives(
    dataset: Dataset, scenario: Scenario, result: Plan, limit: int = LIMIT
) -> list[Alternative]:
    """Plans that swap one used recipe for a rival making the same product."""
    used = used_recipes(result)
    seen: set[frozenset[str]] = {frozenset(used)}
    out: list[Alternative] = []
    for use in result.recipes:
        if use.recipe_id not in used:
            continue
        recipe = dataset.recipes[use.recipe_id]
        for stack in recipe.outputs:
            for rival in candidates(dataset, scenario, stack.item_id):
                if rival.id == recipe.id or len(out) >= limit:
                    continue
                overrides = {**scenario.recipe_overrides, stack.item_id: rival.id}
                variant = scenario.model_copy(update={"recipe_overrides": overrides})
                other = plan(dataset, variant)
                recipes = frozenset(used_recipes(other))
                if other.status == "infeasible" or recipes in seen:
                    continue
                seen.add(recipes)
                out.append(
                    Alternative(
                        item_id=stack.item_id,
                        recipe_id=rival.id,
                        machine_id=rival.machine_id,
                        scenario=variant,
                        status=other.status,
                        machine_count=other.machine_count,
                        footprint_cells=other.footprint_cells,
                        power=other.power,
                        scale=other.scale,
                        recipes=sorted(recipes),
                    )
                )
    out.sort(key=lambda a: (a.status != "ok", a.machine_count, a.footprint_cells))
    log.info("alternatives: %d found over %d used recipe(s)", len(out), len(used))
    return out


def bannable(dataset: Dataset, scenario: Scenario, result: Plan) -> list[str]:
    """Machines of the plan whose ban still leaves the targets feasible."""
    out: list[str] = []
    for machine_id in sorted({u.machine_id for u in result.recipes}):
        if machine_id in scenario.banned_machines:
            continue
        if machine_id in dataset.dumps:
            continue
        variant = scenario.model_copy(
            update={"banned_machines": [*scenario.banned_machines, machine_id]}
        )
        if plan(dataset, variant).status != "infeasible":
            out.append(machine_id)
    log.debug("bannable machines: %s", out)
    return out
