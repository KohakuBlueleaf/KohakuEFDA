"""Scenario → Plan: expand recipes, resolve target intents, solve, then rebuild exact balances,
the total power requirement, nets and cells."""

import logging
import math
from fractions import Fraction

from kohakuefda.flow.nets import build_nets
from kohakuefda.flow.stability import (
    balance_findings,
    resource_findings,
    target_findings,
)
from kohakuefda.model.basement import DEFAULT_SQUARE
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.items import Phase
from kohakuefda.model.plan import (
    Cell,
    Finding,
    ItemBalance,
    Plan,
    RecipeUse,
    TargetResult,
)
from kohakuefda.model.recipes import Recipe
from kohakuefda.model.scenario import TARGET_MAX, Scenario, goal_of
from kohakuefda.model.sinks import ZONE_GAS_PER_MIN, ZONE_MACHINE
from kohakuefda.plan.lp import AREA_FILL, WEIGHTS, LpResult, machine_cost, solve
from kohakuefda.plan.recipes import (
    RecipeGraph,
    effective_supply,
    expand,
    why_unmakeable,
)

log = logging.getLogger(__name__)
Targets = dict[str, Fraction | None]
DUMP_PREFIX = "dump:"


def min_line_rate(
    dataset: Dataset, recipes: list[Recipe], item_id: str, weights: tuple[float, float]
) -> Fraction:
    """One machine's output of ``item_id`` on the maker with the lowest cost per unit made."""
    makers = [r for r in recipes if r.output_rate(item_id) > 0]
    if not makers:
        return Fraction(1)
    best = min(
        makers,
        key=lambda r: (
            machine_cost(dataset, r, weights) / float(r.output_rate(item_id)),
            r.id,
        ),
    )
    return best.output_rate(item_id)


def resolve_targets(
    dataset: Dataset, scenario: Scenario, recipes: list[Recipe]
) -> Targets:
    """Rated targets as fractions, ``min`` as one machine's output, ``max`` as ``None`` (open)."""
    weights = WEIGHTS[scenario.mode]
    out: Targets = {}
    for item_id, spec in scenario.targets.items():
        goal = goal_of(spec)
        if goal is None:
            out[item_id] = spec
        elif goal == TARGET_MAX:
            out[item_id] = None
        else:
            out[item_id] = min_line_rate(dataset, recipes, item_id, weights)
    return out


def area_budget(dataset: Dataset, scenario: Scenario) -> float:
    """Cells the planner may cover with machines: the fill fraction times the square."""
    basement = dataset.basements.get(scenario.basement.basement_id)
    square = (
        basement.square_or_default(scenario.basement.level)
        if basement
        else DEFAULT_SQUARE
    )
    fill = scenario.area_fill if scenario.area_fill is not None else AREA_FILL
    return fill * square[0] * square[1]


def plan(dataset: Dataset, scenario: Scenario) -> Plan:
    """Plan a scenario; the result is exact in fractions even though the solver is floating point."""
    graph = expand(dataset, scenario)
    log.debug(
        "recipe graph: %d recipe(s), %d raw item(s), %d unmakeable",
        len(graph.recipe_ids),
        len(graph.raw_items),
        len(graph.unmakeable),
    )
    findings = _graph_findings(dataset, scenario, graph)
    recipes = [dataset.recipes[r] for r in graph.recipe_ids]
    targets = resolve_targets(dataset, scenario, recipes)
    budget = (
        area_budget(dataset, scenario)
        if any(rate is None for rate in targets.values())
        else None
    )
    result = (
        solve(dataset, scenario, recipes, targets, budget) if recipes else LpResult()
    )
    if not result.feasible:
        blocked = _blocked_targets(dataset, scenario, graph)
        for item_id, reason in blocked.items():
            log.warning("cannot make %s: %s", item_id, reason)
        if not blocked:
            log.warning(
                "plan infeasible with %d candidate recipe(s) for %s: the supply cannot"
                " feed them",
                len(recipes),
                ", ".join(scenario.targets) or "no target",
            )
        return _empty_plan(
            dataset, scenario, findings + _infeasible(dataset, scenario, blocked)
        )
    requested = {
        i: (rate if rate is not None else result.delivered.get(i, Fraction(0)))
        for i, rate in targets.items()
    }
    uses = _uses(dataset, result)
    items = _balances(dataset, scenario, uses, result, requested)
    target_results = [
        TargetResult(
            item_id=i,
            requested=requested[i],
            achieved=items[i].delivered if i in items else Fraction(0),
            goal=goal_of(scenario.targets[i]),
        )
        for i in scenario.targets
    ]
    findings += balance_findings(dataset, items) + target_findings(
        dataset, target_results
    )
    findings += _open_findings(dataset, target_results)
    dump_uses = _dump_uses(dataset, items)
    all_uses = uses + dump_uses
    power = power_draw(dataset, all_uses)
    footprint = sum(
        u.machines
        * dataset.machines[u.machine_id].width
        * dataset.machines[u.machine_id].depth
        for u in all_uses
    )
    zone_machine = dataset.machines[ZONE_MACHINE]
    zone_count = sum(result.zones.values())
    footprint += zone_count * zone_machine.width * zone_machine.depth
    findings += resource_findings(dataset, scenario, uses, power, footprint)
    findings += _env_findings(dataset, result)
    status = _status(scenario, result, target_results)
    machine_count = sum(u.machines for u in all_uses) + zone_count
    log.info(
        "plan %s: scale %s, %d machine(s), power %d, footprint %d cells",
        status,
        result.scale,
        machine_count,
        power,
        footprint,
    )
    return Plan(
        dataset_version=dataset.version.id,
        scenario=scenario,
        status=status,
        scale=result.scale,
        targets=target_results,
        recipes=all_uses,
        items=items,
        nets=build_nets(dataset, uses, items, scenario.activation),
        cells=_cells(dataset, uses),
        findings=findings,
        power=power,
        footprint_cells=footprint,
        machine_count=machine_count,
        zones=dict(result.zones),
    )


def activation_draw(dataset: Dataset, scenario: Scenario, use: RecipeUse) -> Fraction:
    """Activation fluid one recipe use draws: per built machine, or per duty (ACT-03)."""
    activation = dataset.activations.get(use.machine_id)
    if activation is None:
        return Fraction(0)
    count = use.machines_exact if scenario.activation == "duty" else use.machines
    return activation.min_rate * count


def _status(scenario: Scenario, result: LpResult, targets: list[TargetResult]) -> str:
    if not scenario.targets:
        return "ok"
    if result.scale == 0 or all(t.achieved == 0 for t in targets):
        return "infeasible"
    if result.scale < 1 or any(t.achieved == 0 for t in targets):
        return "degraded"
    return "ok"


def _open_findings(dataset: Dataset, targets: list[TargetResult]) -> list[Finding]:
    return [
        Finding(
            rule="plan.degraded",
            severity="warning",
            subject=t.item_id,
            message=f"{dataset.items[t.item_id].names.en}: nothing can be made from the supply",
        )
        for t in targets
        if t.goal == TARGET_MAX and t.achieved == 0
    ]


def _uses(dataset: Dataset, result: LpResult) -> list[RecipeUse]:
    """Recipes with crafts running; ``machines_exact`` is the load in machine-equivalents."""
    uses: list[RecipeUse] = []
    for recipe_id, crafts in result.crafts.items():
        machines = result.machines.get(recipe_id, 0)
        if crafts <= 0 and machines <= 0:
            continue
        recipe = dataset.recipes[recipe_id]
        exact = crafts / recipe.crafts_per_minute
        use = RecipeUse(
            recipe_id=recipe_id,
            machine_id=recipe.machine_id,
            mode=recipe.mode,
            crafts_per_min=crafts,
            machines_exact=exact,
            machines=max(machines, math.ceil(exact)),
        )
        log.debug(
            "recipe use %s: %s crafts/min, %d machine(s)",
            recipe_id,
            crafts,
            use.machines,
        )
        uses.append(use)
    return uses


def power_draw(dataset: Dataset, uses: list[RecipeUse]) -> int:
    """The total power every built machine draws (PWR-05); dump units by their load."""
    return sum(
        (
            math.ceil(u.machines_exact * dataset.machines[u.machine_id].power)
            if u.recipe_id.startswith(DUMP_PREFIX)
            else u.machines * dataset.machines[u.machine_id].power
        )
        for u in uses
    )


def _balances(
    dataset: Dataset,
    scenario: Scenario,
    uses: list[RecipeUse],
    result: LpResult,
    requested: dict[str, Fraction],
) -> dict[str, ItemBalance]:
    """Exact per-item balances recomputed from the snapped craft rates."""
    sources = effective_supply(dataset, scenario)
    produced: dict[str, Fraction] = {}
    consumed: dict[str, Fraction] = {}
    for use in uses:
        recipe = dataset.recipes[use.recipe_id]
        for stack in recipe.outputs:
            produced[stack.item_id] = (
                produced.get(stack.item_id, Fraction(0))
                + stack.count * use.crafts_per_min
            )
        for stack in recipe.inputs:
            consumed[stack.item_id] = (
                consumed.get(stack.item_id, Fraction(0))
                + stack.count * use.crafts_per_min
            )
        activation = dataset.activations.get(use.machine_id)
        if activation:
            consumed[activation.item_id] = consumed.get(
                activation.item_id, Fraction(0)
            ) + activation_draw(dataset, scenario, use)
    for env, count in result.zones.items():
        gas = dataset.env_gases.get(env)
        if gas:
            consumed[gas] = consumed.get(gas, Fraction(0)) + ZONE_GAS_PER_MIN * count
    items: dict[str, ItemBalance] = {}
    for item_id in sorted(set(produced) | set(consumed) | set(requested)):
        made = produced.get(item_id, Fraction(0))
        used = consumed.get(item_id, Fraction(0))
        supplied = Fraction(0)
        if item_id in sources and used > made:
            supplied = used - made
        available = made + supplied - used
        delivered = (
            min(available, requested[item_id]) if item_id in requested else Fraction(0)
        )
        delivered = max(delivered, Fraction(0))
        surplus = available - delivered
        sunk, kind = _sink(dataset, item_id, surplus)
        items[item_id] = ItemBalance(
            item_id=item_id,
            produced=made,
            consumed=used,
            supplied=supplied,
            delivered=delivered,
            sunk=sunk,
            sink_kind=kind,
            net=available - delivered - sunk,
        )
    return items


def _sink(
    dataset: Dataset, item_id: str, surplus: Fraction
) -> tuple[Fraction, str | None]:
    if surplus <= 0:
        return Fraction(0), None
    if dataset.items[item_id].phase is Phase.SOLID:
        return surplus, "depot"
    if dataset.dump_for(item_id) is not None:
        return surplus, "dump"
    return Fraction(0), None


def _dump_uses(dataset: Dataset, items: dict[str, ItemBalance]) -> list[RecipeUse]:
    """Water Treatment Units (or similar) needed for dumped fluids, as pseudo recipe uses."""
    per_machine: dict[str, Fraction] = {}
    for balance in items.values():
        if balance.sink_kind != "dump":
            continue
        sink = dataset.dump_for(balance.item_id)
        per_machine[sink.machine_id] = (
            per_machine.get(sink.machine_id, Fraction(0))
            + balance.sunk / sink.rate_per_machine
        )
    return [
        RecipeUse(
            recipe_id=f"{DUMP_PREFIX}{machine_id}",
            machine_id=machine_id,
            mode="dump",
            crafts_per_min=exact * dataset.dumps[machine_id].rate_per_machine,
            machines_exact=exact,
            machines=math.ceil(exact),
        )
        for machine_id, exact in per_machine.items()
    ]


def _cells(dataset: Dataset, uses: list[RecipeUse]) -> list[Cell]:
    cells: list[Cell] = []
    for use in uses:
        recipe = dataset.recipes[use.recipe_id]
        cells.append(
            Cell(
                recipe_id=use.recipe_id,
                machine_id=use.machine_id,
                mode=use.mode,
                count=use.machines,
                inputs={s.item_id: recipe.input_rate(s.item_id) for s in recipe.inputs},
                outputs={
                    s.item_id: recipe.output_rate(s.item_id) for s in recipe.outputs
                },
            )
        )
    return cells


def _graph_findings(
    dataset: Dataset, scenario: Scenario, graph: RecipeGraph
) -> list[Finding]:
    return [
        Finding(
            rule="plan.unsupplied",
            severity="info",
            subject=item_id,
            message=(
                f"{why_unmakeable(dataset, scenario, item_id)}; recipes that need it stay unused"
            ),
        )
        for item_id in graph.unmakeable
    ]


def _env_findings(dataset: Dataset, result: LpResult) -> list[Finding]:
    return [
        Finding(
            rule="flow.env_zone",
            severity="info",
            subject=env,
            message=f"{count} Gas Dispersing Unit zone(s) ({env}), each fed 6/min of {dataset.items[dataset.env_gases[env]].names.en}",
        )
        for env, count in result.zones.items()
        if env in dataset.env_gases
    ]


def _blocked_targets(
    dataset: Dataset, scenario: Scenario, graph: RecipeGraph
) -> dict[str, str]:
    """Targets nothing can make here, each with the reason the filter gives."""
    unmakeable = set(graph.unmakeable)
    return {
        item_id: why_unmakeable(dataset, scenario, item_id)
        for item_id in scenario.targets
        if item_id in unmakeable
    }


def _infeasible(
    dataset: Dataset, scenario: Scenario, blocked: dict[str, str]
) -> list[Finding]:
    """One finding per target that cannot be made, else one saying the supply is short."""
    if blocked:
        return [
            Finding(
                rule="plan.infeasible",
                severity="error",
                subject=item_id,
                message=reason,
            )
            for item_id, reason in blocked.items()
        ]
    return [
        Finding(
            rule="plan.infeasible",
            severity="error",
            subject="plan",
            message=(
                "every target has a recipe, but the supply cannot feed them; raise a supply"
                " rate or lower a target"
            ),
        )
    ]


def _empty_plan(dataset: Dataset, scenario: Scenario, findings: list[Finding]) -> Plan:
    return Plan(
        dataset_version=dataset.version.id,
        scenario=scenario,
        status="infeasible",
        scale=Fraction(0),
        targets=[
            TargetResult(
                item_id=i,
                requested=spec if goal_of(spec) is None else Fraction(0),
                achieved=Fraction(0),
                goal=goal_of(spec),
            )
            for i, spec in scenario.targets.items()
        ],
        recipes=[],
        items={},
        nets=[],
        cells=[],
        findings=findings,
        power=0,
        footprint_cells=0,
        machine_count=0,
    )
