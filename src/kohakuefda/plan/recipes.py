"""Which recipes a scenario may use, what the world supplies, and the recipe graph reachable
from its targets.

Facts: game-knowledge RCP-06 (event recipes), RES-01 (natural resources), REG-01 (regions).
"""

import logging
from collections import Counter, deque
from fractions import Fraction

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.basement import Region
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.items import Phase
from kohakuefda.model.recipes import Recipe
from kohakuefda.model.scenario import Scenario

log = logging.getLogger(__name__)
GAS_MODES = {"gas", "gasliquid", "gastrans", "solidtrans", "liquidtrans"}
FLUID_MODES = GAS_MODES | {"liquid"}
Supply = dict[str, Fraction | None]


class RecipeGraph(EfdaModel):
    """Recipes reachable from the targets, raw items, and items that cannot be made."""

    recipe_ids: list[str]
    raw_items: list[str]
    unmakeable: list[str]


def _uses_phase(dataset: Dataset, recipe: Recipe, phases: set[Phase]) -> bool:
    return any(
        dataset.items[s.item_id].phase in phases for s in recipe.inputs + recipe.outputs
    )


def rejection(dataset: Dataset, scenario: Scenario, recipe: Recipe) -> str | None:
    """Why the scenario may not use ``recipe``, in the user's terms, or ``None`` when it may."""
    machine = dataset.machines[recipe.machine_id]
    if machine.id in scenario.banned_machines:
        return f"{machine.names.en} is banned"
    if recipe.event and not scenario.events:
        return "it is a limited-time event recipe"
    if scenario.basement.region is Region.VALLEY4:
        if machine.place_domains and "domain_1" not in machine.place_domains:
            return f"{machine.names.en} cannot be built in Valley IV"
        if recipe.mode in FLUID_MODES or _uses_phase(
            dataset, recipe, {Phase.LIQUID, Phase.GAS}
        ):
            return "Valley IV has no fluid recipes"
    if not scenario.gas and (
        recipe.mode in GAS_MODES
        or recipe.env is not None
        or _uses_phase(dataset, recipe, {Phase.GAS})
    ):
        return "gas machines are turned off"
    if not scenario.liquids and (
        recipe.mode in FLUID_MODES
        or _uses_phase(dataset, recipe, {Phase.LIQUID, Phase.GAS})
    ):
        return "liquid machines are turned off"
    return None


def allowed(dataset: Dataset, scenario: Scenario, recipe: Recipe) -> bool:
    """Region, phase-flag, event, banned-machine and machine-availability filter for one recipe."""
    return rejection(dataset, scenario, recipe) is None


def why_unmakeable(dataset: Dataset, scenario: Scenario, item_id: str) -> str:
    """Why nothing can make ``item_id`` here: no recipe at all, or every one filtered out."""
    name = dataset.items[item_id].names.en
    recipes = [r for r in dataset.recipes_for(item_id) if r.output_rate(item_id) > 0]
    if not recipes:
        return f"nothing in the factory makes {name}; it has to come from the depot"
    reasons = Counter(
        rejection(dataset, scenario, r) or "it is available" for r in recipes
    )
    detail = ", ".join(f"{reason} ({count})" for reason, count in reasons.most_common())
    return f"all {len(recipes)} recipe(s) for {name} are unavailable: {detail}"


def effective_supply(dataset: Dataset, scenario: Scenario) -> Supply:
    """The scenario's supply plus every natural resource its defaults make plenty.

    Ores and liquids the world supplies are plenty when ``natural_default`` is ``plenty``; vent
    gases when ``gas_default`` is ``plenty`` and gas is allowed; a Valley IV line never gets
    fluids this way. An item listed in ``supply`` keeps its own cap.
    """
    supply: Supply = dict(scenario.supply)
    valley = scenario.basement.region is Region.VALLEY4
    for item_id in dataset.resources:
        if item_id in supply:
            continue
        phase = dataset.items[item_id].phase
        if phase is Phase.GAS:
            if scenario.gas and scenario.gas_default == "plenty" and not valley:
                supply[item_id] = None
        elif phase is Phase.LIQUID:
            if scenario.natural_default == "plenty" and scenario.liquids and not valley:
                supply[item_id] = None
        elif scenario.natural_default == "plenty":
            supply[item_id] = None
    return supply


def candidates(dataset: Dataset, scenario: Scenario, item_id: str) -> list[Recipe]:
    """Recipes that may produce ``item_id``; an explicit override wins outright."""
    override = scenario.recipe_overrides.get(item_id)
    if override:
        return [dataset.recipes[override]]
    return [
        r
        for r in dataset.recipes_for(item_id)
        if allowed(dataset, scenario, r) and r.output_rate(item_id) > 0
    ]


def is_raw(dataset: Dataset, scenario: Scenario, item_id: str) -> bool:
    return item_id in effective_supply(dataset, scenario)


def expand(dataset: Dataset, scenario: Scenario) -> RecipeGraph:
    """Breadth-first expansion from the targets through candidate recipes."""
    supply = effective_supply(dataset, scenario)
    recipe_ids: dict[str, None] = {}
    raw: dict[str, None] = {}
    unmakeable: dict[str, None] = {}
    seen: set[str] = set()
    queue = deque(scenario.targets)
    while queue:
        item_id = queue.popleft()
        if item_id in seen:
            continue
        seen.add(item_id)
        if item_id in supply:
            raw[item_id] = None
            continue
        found = candidates(dataset, scenario, item_id)
        if not found:
            unmakeable[item_id] = None
            continue
        for recipe in found:
            recipe_ids[recipe.id] = None
            for stack in recipe.inputs:
                queue.append(stack.item_id)
    if unmakeable:
        log.debug("unmakeable items reached by expansion: %s", sorted(unmakeable))
    return RecipeGraph(
        recipe_ids=list(recipe_ids), raw_items=list(raw), unmakeable=list(unmakeable)
    )
