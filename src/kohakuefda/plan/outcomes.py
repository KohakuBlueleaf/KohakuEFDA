"""What a plan needs and what comes out of it, in the player's terms.

``requirements`` sorts the items the targets need from outside into natural resources (the
world supplies them: ores, water, acid, vent gases), gathered items (nothing in the factory
makes them, the player brings them by hand) and intermediates that could be supplied instead of
made. ``outcomes`` lists every flow that leaves the line (delivered, stored in the depot,
dumped) and every supply it draws, each with the next products the recipe graph could turn it
into.
"""

import logging
from fractions import Fraction
from typing import Literal

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Plan
from kohakuefda.model.rates import Rate
from kohakuefda.model.scenario import Scenario, TargetGoal, goal_of
from kohakuefda.plan.recipes import allowed, expand

log = logging.getLogger(__name__)
OutcomeKind = Literal["delivered", "stored", "dumped", "consumed", "missing"]


class NextProduct(EfdaModel):
    """A recipe that consumes an outcome item and one product it makes from it."""

    recipe_id: str
    machine_id: str
    product_id: str
    ratio: Rate
    rate: Rate
    inputs: list[str] = []


class Outcome(EfdaModel):
    """One flow leaving or entering the line and what it could become."""

    item_id: str
    kind: OutcomeKind
    rate: Rate
    goal: TargetGoal | None = None
    sink_machine: str | None = None
    next: list[NextProduct] = []


class Requirements(EfdaModel):
    """Natural resources and hand-gathered items the targets need; intermediates that could be supplied."""

    natural: list[str]
    gathered: list[str]
    intermediates: list[str]


def next_products(
    dataset: Dataset, scenario: Scenario, item_id: str, flow: Fraction
) -> list[NextProduct]:
    """Every allowed recipe consuming ``item_id``, one entry per product, sized to ``flow``."""
    out: list[NextProduct] = []
    for recipe in sorted(dataset.recipes.values(), key=lambda r: r.id):
        needed = recipe.input_rate(item_id)
        if needed <= 0 or not allowed(dataset, scenario, recipe):
            continue
        for stack in recipe.outputs:
            if stack.item_id == item_id:
                continue
            ratio = recipe.output_rate(stack.item_id) / needed
            out.append(
                NextProduct(
                    recipe_id=recipe.id,
                    machine_id=recipe.machine_id,
                    product_id=stack.item_id,
                    ratio=ratio,
                    rate=flow * ratio,
                    inputs=[s.item_id for s in recipe.inputs if s.item_id != item_id],
                )
            )
    return out


def outcomes(dataset: Dataset, scenario: Scenario, plan: Plan) -> list[Outcome]:
    """Delivered, stored, dumped and consumed flows of ``plan``, then targets nothing reached."""
    goals = {i: goal_of(spec) for i, spec in scenario.targets.items()}
    delivered: list[Outcome] = []
    stored: list[Outcome] = []
    dumped: list[Outcome] = []
    consumed: list[Outcome] = []
    for item_id, balance in plan.items.items():
        if balance.delivered > 0:
            delivered.append(
                Outcome(
                    item_id=item_id,
                    kind="delivered",
                    rate=balance.delivered,
                    goal=goals.get(item_id),
                    next=next_products(dataset, scenario, item_id, balance.delivered),
                )
            )
        if balance.sunk > 0:
            sink = dataset.dump_for(item_id) if balance.sink_kind == "dump" else None
            bucket = dumped if balance.sink_kind == "dump" else stored
            bucket.append(
                Outcome(
                    item_id=item_id,
                    kind="dumped" if balance.sink_kind == "dump" else "stored",
                    rate=balance.sunk,
                    sink_machine=sink.machine_id if sink else None,
                    next=next_products(dataset, scenario, item_id, balance.sunk),
                )
            )
        if balance.supplied > 0:
            consumed.append(
                Outcome(item_id=item_id, kind="consumed", rate=balance.supplied)
            )
    reached = {o.item_id for o in delivered}
    missing = [
        Outcome(item_id=t.item_id, kind="missing", rate=Fraction(0), goal=t.goal)
        for t in plan.targets
        if t.item_id not in reached
    ]
    log.debug(
        "outcomes: %d delivered, %d stored, %d dumped, %d consumed, %d missing",
        len(delivered),
        len(stored),
        len(dumped),
        len(consumed),
        len(missing),
    )
    return delivered + stored + dumped + consumed + missing


def requirements(dataset: Dataset, scenario: Scenario) -> Requirements:
    """What the targets need from outside, split by where it comes from, and the intermediates.

    Every natural resource any reachable recipe consumes is listed, even one some recipe also
    makes as a by-product (water, acid): the world supplies it, the line should not loop for it.
    """
    bare = scenario.model_copy(
        update={"supply": {}, "natural_default": "none", "gas_default": "none"}
    )
    graph = expand(dataset, bare)
    made: set[str] = set()
    used: set[str] = set()
    for recipe_id in graph.recipe_ids:
        recipe = dataset.recipes[recipe_id]
        made.update(s.item_id for s in recipe.outputs)
        used.update(s.item_id for s in recipe.inputs)
        activation = dataset.activations.get(recipe.machine_id)
        if activation:
            used.add(activation.item_id)
        if recipe.env and recipe.env in dataset.env_gases:
            used.add(dataset.env_gases[recipe.env])
    natural = sorted(i for i in used | set(graph.unmakeable) if dataset.is_resource(i))
    gathered = sorted(i for i in graph.unmakeable if not dataset.is_resource(i))
    intermediates = sorted(made - set(natural) - set(gathered) - set(scenario.targets))
    log.debug(
        "requirements: %d natural, %d gathered, %d intermediate",
        len(natural),
        len(gathered),
        len(intermediates),
    )
    return Requirements(natural=natural, gathered=gathered, intermediates=intermediates)
