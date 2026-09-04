"""HiGHS model: whole machines per recipe, crafts per minute, sinks, sources, zones and area.

Every recipe has two variables: ``f`` (crafts per minute, continuous) and ``x`` (machines,
integer when ``WHOLE_MACHINES``) with ``f ≤ crafts_per_minute × x``. Item balances are written
in crafts, so a stack of 2 per craft contributes 2 × f. A transmuter's activation draw is
charged per built machine (``activation = "built"``, game-knowledge ACT-03) or per duty. An
environment needs an integer number of Gas Dispersing Units, each a 13×13 zone (ENV-01) that
holds at most ``ZONE_FILL`` of its cells in machine footprint; every zone draws its gas and
counts as a machine. Sources are the effective supply: what the player listed plus the natural
resources the scenario's defaults make plenty (RES-01). Targets are rated (an upper bound) or
open (``None``). Three solves on one model: maximise the common scale of the rated targets,
then the delivered target rate (open targets weighted by their reference rate), then minimise
machine, zone and dump cost, where drawing from the depot or the world costs the unloader or
pump lane it needs and storing in the depot costs the loader lane, with two tie-breaks a
player would apply: less power drawn and fewer distinct recipes built. An area budget caps the
machine footprint so open targets stay bounded. Power is only ever summed (PWR-05).
"""

import logging
from fractions import Fraction

import highspy

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.items import Phase
from kohakuefda.model.recipes import Recipe
from kohakuefda.model.scenario import PlanMode, Scenario
from kohakuefda.model.sinks import (
    GAS_PUMP,
    LIQUID_PUMP,
    SOURCE_RATES,
    ZONE_GAS_PER_MIN,
    ZONE_MACHINE,
    ZONE_SIDE,
)
from kohakuefda.plan.recipes import Supply, effective_supply

log = logging.getLogger(__name__)
INF = highspy.kHighsInf
BIG = 100000.0
POWER_COST = 1e-3
SETUP_COST = 0.05
ZONE_FILL = 0.5
UNLOADER = "unloader_1"
LOADER = "loader_1"
SNAP_DENOMINATOR = 3600
ZERO_TOL = 1e-7
AREA_FILL = 0.5
WHOLE_MACHINES = True
WEIGHTS: dict[PlanMode, tuple[float, float]] = {
    PlanMode.MACHINES: (1.0, 0.0),
    PlanMode.AREA: (0.05, 1.0),
    PlanMode.BALANCED: (1.0, 1.0 / 9.0),
}
Targets = dict[str, Fraction | None]


class LpResult:
    """Solution in exact fractions: crafts and machines per recipe, delivery, zones, dumps."""

    def __init__(self) -> None:
        self.feasible = False
        self.scale = Fraction(0)
        self.crafts: dict[str, Fraction] = {}
        self.machines: dict[str, int] = {}
        self.delivered: dict[str, Fraction] = {}
        self.envs_used: list[str] = []
        self.zones: dict[str, int] = {}
        self.dump_rates: dict[str, Fraction] = {}


def _snap(value: float) -> Fraction:
    if abs(value) < ZERO_TOL:
        return Fraction(0)
    return Fraction(value).limit_denominator(SNAP_DENOMINATOR)


def _area(dataset: Dataset, machine_id: str) -> int:
    machine = dataset.machines[machine_id]
    return machine.width * machine.depth


def machine_cost(
    dataset: Dataset, recipe: Recipe, weights: tuple[float, float]
) -> float:
    """Cost of one machine running ``recipe``; the ``x`` variables count machines."""
    return unit_cost(dataset, recipe.machine_id, weights)


def unit_cost(dataset: Dataset, machine_id: str, weights: tuple[float, float]) -> float:
    w_machine, w_area = weights
    return w_machine + w_area * _area(dataset, machine_id)


def source_cost(dataset: Dataset, item_id: str, weights: tuple[float, float]) -> float:
    """Cost per unit per minute of drawing ``item_id``: the unloader or pump lane it needs."""
    phase = dataset.items[item_id].phase
    if phase is Phase.SOLID:
        return unit_cost(dataset, UNLOADER, weights) / float(
            dataset.constants.belt_per_min
        )
    pump = GAS_PUMP if phase is Phase.GAS else LIQUID_PUMP
    return unit_cost(dataset, pump, weights) / float(SOURCE_RATES[pump])


def reference_rate(recipes: list[Recipe], item_id: str) -> Fraction:
    """The largest per-machine output of ``item_id`` among ``recipes`` (1 when none makes it)."""
    rates = [r.output_rate(item_id) for r in recipes if r.output_rate(item_id) > 0]
    return max(rates) if rates else Fraction(1)


def _optimal(model: highspy.Highs) -> bool:
    return model.getModelStatus() == highspy.HighsModelStatus.kOptimal


def solve(
    dataset: Dataset,
    scenario: Scenario,
    recipes: list[Recipe],
    targets: Targets,
    area_budget: float | None = None,
    whole_machines: bool = WHOLE_MACHINES,
) -> LpResult:
    """Solve the planning MILP; see the module docstring for the phases."""
    model = highspy.Highs()
    model.silent()
    integer = highspy.HighsVarType.kInteger
    sources = effective_supply(dataset, scenario)
    items = _universe(dataset, sources, recipes, targets)
    log.debug(
        "MILP model: %d recipe(s), %d item(s), %d source(s), whole_machines=%s",
        len(recipes),
        len(items),
        len(sources),
        whole_machines,
    )
    f = {r.id: model.addVariable(lb=0, ub=INF) for r in recipes}
    x = {
        r.id: (
            model.addVariable(lb=0, ub=INF, type=integer)
            if whole_machines
            else model.addVariable(lb=0, ub=INF)
        )
        for r in recipes
    }
    for recipe in recipes:
        model.addConstr(
            f[recipe.id] - float(recipe.crafts_per_minute) * x[recipe.id] <= 0
        )
    supply = {
        i: model.addVariable(lb=0, ub=_supply_cap(sources, i))
        for i in items
        if i in sources
    }
    target = {
        i: model.addVariable(lb=0, ub=INF if rate is None else float(rate))
        for i, rate in targets.items()
    }
    depot = {
        i: model.addVariable(lb=0, ub=INF)
        for i in items
        if dataset.items[i].phase is Phase.SOLID
    }
    dump = {
        i: model.addVariable(lb=0, ub=INF)
        for i in items
        if dataset.dump_for(i) is not None
    }
    envs = sorted({r.env for r in recipes if r.env})
    env_used = {e: model.addVariable(lb=0, ub=1, type=integer) for e in envs}
    zones = {e: model.addVariable(lb=0, ub=INF, type=integer) for e in envs}
    zone_cells = ZONE_SIDE * ZONE_SIDE * ZONE_FILL
    for env, var in env_used.items():
        env_area = 0
        for recipe in recipes:
            if recipe.env == env:
                model.addConstr(x[recipe.id] <= BIG * var)
                env_area = env_area + _area(dataset, recipe.machine_id) * x[recipe.id]
        model.addConstr(zone_cells * zones[env] - env_area >= 0)
        model.addConstr(zones[env] <= BIG * var)
        model.addConstr(zones[env] - var >= 0)
    built = {r.id: model.addVariable(lb=0, ub=1, type=integer) for r in recipes}
    for recipe in recipes:
        model.addConstr(x[recipe.id] <= BIG * built[recipe.id])
    for item_id in items:
        expr = 0
        for recipe in recipes:
            per_craft = _count(recipe.outputs, item_id) - _count(recipe.inputs, item_id)
            if per_craft:
                expr = expr + float(per_craft) * f[recipe.id]
            activation = dataset.activations.get(recipe.machine_id)
            if activation and activation.item_id == item_id:
                if scenario.activation == "duty":
                    expr = expr - (
                        float(activation.min_rate / recipe.crafts_per_minute)
                        * f[recipe.id]
                    )
                else:
                    expr = expr - float(activation.min_rate) * x[recipe.id]
        for env, gas in dataset.env_gases.items():
            if gas == item_id and env in zones:
                expr = expr - float(ZONE_GAS_PER_MIN) * zones[env]
        if item_id in supply:
            expr = expr + supply[item_id]
        if item_id in target:
            expr = expr - target[item_id]
        if item_id in depot:
            expr = expr - depot[item_id]
        if item_id in dump:
            expr = expr - dump[item_id]
        model.addConstr(expr == 0)
    draw = sum(dataset.machines[r.machine_id].power * x[r.id] for r in recipes)
    for item_id, var in dump.items():
        sink = dataset.dump_for(item_id)
        draw = (
            draw
            + (dataset.machines[sink.machine_id].power / float(sink.rate_per_machine))
            * var
        )
    if area_budget is not None and recipes:
        area = sum(_area(dataset, r.machine_id) * x[r.id] for r in recipes)
        model.addConstr(area <= float(area_budget))
    result = LpResult()
    if not target:
        result.feasible = True
        result.scale = Fraction(1)
        return result
    rated = {i: rate for i, rate in targets.items() if rate is not None}
    scale = 1.0
    if rated:
        z = model.addVariable(lb=0, ub=1)
        for item_id, rate in rated.items():
            model.addConstr(target[item_id] - float(rate) * z >= 0)
        model.maximize(z)
        if not _optimal(model):
            log.warning(
                "MILP infeasible in the scale phase over %d rated target(s)", len(rated)
            )
            return result
        scale = model.val(z)
        model.addConstr(z >= scale - 1e-9)
        log.debug(
            "scale phase: common scale %.4f over %d rated target(s)", scale, len(rated)
        )
    reference = {
        i: float(rate) if rate is not None else float(reference_rate(recipes, i))
        for i, rate in targets.items()
    }
    model.maximize(sum(var * (1.0 / reference[i]) for i, var in target.items()))
    if not _optimal(model):
        log.warning("MILP infeasible in the delivery phase")
        return result
    delivered = {i: model.val(var) for i, var in target.items()}
    log.debug("delivery phase: %s", delivered)
    for item_id, var in target.items():
        model.addConstr(var >= delivered[item_id] - 1e-9)
    weights = WEIGHTS[scenario.mode]
    belt = dataset.constants.belt_per_min
    cost = sum(machine_cost(dataset, r, weights) * x[r.id] for r in recipes)
    for item_id, var in dump.items():
        sink = dataset.dump_for(item_id)
        per_unit = unit_cost(dataset, sink.machine_id, weights) / float(
            sink.rate_per_machine
        )
        cost = cost + per_unit * var
    for var in zones.values():
        cost = cost + unit_cost(dataset, ZONE_MACHINE, weights) * var
    for item_id, var in supply.items():
        cost = cost + source_cost(dataset, item_id, weights) * var
    for var in depot.values():
        cost = cost + unit_cost(dataset, LOADER, weights) / float(belt) * var
    cost = cost + POWER_COST * draw
    cost = cost + sum(SETUP_COST * var for var in built.values())
    model.minimize(cost)
    if not _optimal(model):
        log.warning("MILP infeasible in the cost phase")
        return result
    result.feasible = True
    result.scale = _snap(scale)
    result.crafts = {r.id: _snap(model.val(f[r.id])) for r in recipes}
    result.machines = {r.id: round(model.val(x[r.id])) for r in recipes}
    result.delivered = {i: _snap(model.val(var)) for i, var in target.items()}
    result.envs_used = [e for e, var in env_used.items() if model.val(var) > 0.5]
    log.debug(
        "cost phase: %d machine(s) built, %d zone(s) used",
        sum(result.machines.values()),
        len(result.envs_used),
    )
    result.zones = {
        e: round(model.val(var)) for e, var in zones.items() if model.val(var) > 0.5
    }
    result.dump_rates = {i: _snap(model.val(var)) for i, var in dump.items()}
    return result


def _count(stacks: list, item_id: str) -> int:
    return sum(s.count for s in stacks if s.item_id == item_id)


def _supply_cap(sources: Supply, item_id: str) -> float:
    cap = sources[item_id]
    return INF if cap is None else float(cap)


def _universe(
    dataset: Dataset, sources: Supply, recipes: list[Recipe], targets: Targets
) -> list[str]:
    """Every item that can carry flow: recipe items, activation fluids, gases, targets, supply."""
    items: dict[str, None] = {}
    for recipe in recipes:
        for stack in recipe.inputs + recipe.outputs:
            items[stack.item_id] = None
        activation = dataset.activations.get(recipe.machine_id)
        if activation:
            items[activation.item_id] = None
        if recipe.env and recipe.env in dataset.env_gases:
            items[dataset.env_gases[recipe.env]] = None
    for item_id in list(targets) + list(sources):
        items[item_id] = None
    return list(items)
