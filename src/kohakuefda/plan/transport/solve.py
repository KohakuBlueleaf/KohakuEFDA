"""Joint machine duties and direct belt allocation under physical port budgets."""

import math
import time
from collections import defaultdict
from fractions import Fraction
from itertools import pairwise
from typing import Any

import highspy

from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.machines import PortDir, PortType
from kohakuefda.plan.transport.domains import allowed_ports, match_ports, unions
from kohakuefda.plan.transport.model import (
    Transfer,
    TransportError,
    TransportResult,
    fingerprint,
)

SECONDS = 5.0
DENOMINATOR = 36000
MAX_EDGES = 20000


def endpoint_rates(net: Any, direction: str) -> dict[str, Fraction]:
    """Aggregate a project's declared lanes at each machine endpoint."""
    out: dict[str, Fraction] = defaultdict(Fraction)
    for ref in net.sources if direction == "out" else net.sinks:
        out[ref.cell_id] += ref.rate
    return dict(out)


def port_count(dataset: Dataset, cell: Any, direction: str) -> int:
    """The number of physical solid ports, including unused ports of a facility."""
    machine = dataset.machines.get(cell.machine_id)
    if machine is None:
        return 0
    return len(machine.ports_of(PortDir(direction), PortType.BELT))


def duty_of(dataset: Dataset, cell: Any) -> Fraction | None:
    """Infer a recipe's declared activity from its solid output lanes."""
    recipe = dataset.recipes.get(cell.recipe_id)
    if recipe is None:
        return None
    total: dict[str, Fraction] = defaultdict(Fraction)
    for pin in cell.pins:
        if pin.direction == "out" and pin.kind == "belt":
            total[pin.item_id] += pin.rate
    values = {
        rate / recipe.output_rate(item)
        for item, rate in total.items()
        if recipe.output_rate(item)
    }
    return next(iter(values)) if len(values) == 1 else None


def allocate(
    dataset: Dataset, netlist: Netlist, seconds: float = SECONDS
) -> TransportResult:
    """Minimise physical belt lanes while preserving recipe activity and every item balance."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise TransportError("the transport solve needs a finite positive time budget")
    started = time.monotonic()
    cells = {cell.id: cell for cell in netlist.cells}
    adjustable = {
        cell.id: duty
        for cell in netlist.cells
        if cell.kind == "recipe"
        and not any(p.kind == "pipe" for p in cell.pins)
        and (duty := duty_of(dataset, cell)) is not None
    }
    nets = [n for n in netlist.nets if n.kind == "belt" and n.rate > 0]
    pairs = [(n, endpoint_rates(n, "out"), endpoint_rates(n, "in")) for n in nets]
    edges = sum(len(s) * len(t) for _, s, t in pairs)
    if edges > MAX_EDGES:
        return TransportResult(
            reason=f"{edges} candidate edges exceed the {MAX_EDGES} edge budget"
        )
    model = highspy.Highs()
    model.silent()
    model.setOptionValue("time_limit", seconds)
    model.setOptionValue("mip_rel_gap", 0.0)
    model.setOptionValue("random_seed", 0)
    model.setOptionValue("parallel", "off")
    duties = {key: model.addVariable(lb=0, ub=1) for key in adjustable}
    by_recipe: dict[str, list[str]] = defaultdict(list)
    for key in adjustable:
        by_recipe[cells[key].recipe_id].append(key)
    for keys in by_recipe.values():
        model.addConstr(
            sum(duties[k] for k in keys)
            == float(sum((adjustable[k] for k in keys), Fraction(0)))
        )
        for first, second in pairwise(keys):
            model.addConstr(duties[first] >= duties[second])
    capacity = dataset.constants.belt_per_min
    transfers: list[tuple[str, str, str, Any, Any]] = []
    use_ports: dict[tuple[str, str], list[Any]] = defaultdict(list)
    domain_use: dict[tuple[str, str], list[tuple[frozenset[int], Any]]] = defaultdict(
        list
    )
    expected: dict[tuple[str, str, str], tuple[Fraction, bool]] = {}
    for net, sources, sinks in pairs:
        incoming: dict[str, list[Any]] = defaultdict(list)
        outgoing: dict[str, list[Any]] = defaultdict(list)
        for source in sources:
            for sink in sinks:
                if source == sink:
                    continue
                source_domain = frozenset(
                    p.index
                    for p in allowed_ports(dataset, cells[source], net.item_id, "out")
                )
                sink_domain = frozenset(
                    p.index
                    for p in allowed_ports(dataset, cells[sink], net.item_id, "in")
                )
                ports = min(len(source_domain), len(sink_domain))
                if not ports:
                    continue
                rate = model.addVariable(lb=0, ub=float(capacity * ports))
                lanes = model.addVariable(
                    lb=0, ub=ports, type=highspy.HighsVarType.kInteger
                )
                model.addConstr(rate <= float(capacity) * lanes)
                outgoing[source].append(rate)
                incoming[sink].append(rate)
                use_ports[source, "out"].append(lanes)
                use_ports[sink, "in"].append(lanes)
                domain_use[source, "out"].append((source_domain, lanes))
                domain_use[sink, "in"].append((sink_domain, lanes))
                transfers.append((net.id, source, sink, rate, lanes))
        for direction, ends, flows in (
            ("out", sources, outgoing),
            ("in", sinks, incoming),
        ):
            for key, nominal in ends.items():
                if key in duties:
                    recipe = dataset.recipes[cells[key].recipe_id]
                    coefficient = (
                        recipe.output_rate(net.item_id)
                        if direction == "out"
                        else recipe.input_rate(net.item_id)
                    )
                    rhs = float(coefficient) * duties[key]
                    expected[net.id, key, direction] = (coefficient, True)
                else:
                    rhs = float(nominal)
                    expected[net.id, key, direction] = (nominal, False)
                if not flows[key]:
                    return TransportResult(
                        reason=f"no direct port candidate for {key} on {net.id}"
                    )
                model.addConstr(sum(flows[key]) == rhs)
    for (cell_id, direction), variables in use_ports.items():
        model.addConstr(
            sum(variables) <= port_count(dataset, cells[cell_id], direction)
        )
    for entries in domain_use.values():
        for domain in unions(d for d, _ in entries):
            model.addConstr(
                sum(var for subset, var in entries if subset <= domain) <= len(domain)
            )
    if not transfers:
        return TransportResult(reason="no positive solid transfers")
    model.minimize(sum(lanes for *_, lanes in transfers))
    result = TransportResult(
        source_digest=fingerprint(netlist), seconds=time.monotonic() - started
    )
    if not model.getSolution().value_valid:
        result.reason = f"no direct-port incumbent: {model.modelStatusToString(model.getModelStatus())}"
        return result
    result.duties = {
        key: Fraction(model.val(var)).limit_denominator(DENOMINATOR)
        for key, var in duties.items()
    }
    for net, source, sink, rate, _ in transfers:
        value = Fraction(model.val(rate)).limit_denominator(DENOMINATOR)
        if value > 0:
            result.transfers.append(Transfer(net, source, sink, value))
            result.lanes += math.ceil(value / capacity)
    actual: dict[tuple[str, str, str], Fraction] = defaultdict(Fraction)
    ports_used: dict[tuple[str, str], int] = defaultdict(int)
    for transfer in result.transfers:
        for direction, key in (("out", transfer.source), ("in", transfer.sink)):
            actual[transfer.net, key, direction] += transfer.rate
            ports_used[key, direction] += math.ceil(transfer.rate / capacity)
    for (net, key, direction), (coefficient, variable) in expected.items():
        wanted = coefficient * result.duties[key] if variable else coefficient
        if actual[net, key, direction] != wanted:
            result.reason = f"rational reconstruction failed at {net}:{key}:{direction}"
            return result
    for keys in by_recipe.values():
        if sum((result.duties[k] for k in keys), Fraction(0)) != sum(
            (adjustable[k] for k in keys), Fraction(0)
        ):
            result.reason = "rational reconstruction changed a recipe's total activity"
            return result
    if any(
        used > port_count(dataset, cells[key], direction)
        for (key, direction), used in ports_used.items()
    ):
        result.reason = "rational reconstruction exceeded a physical port budget"
        return result
    domains: dict[tuple[str, str], list[tuple[int, ...]]] = defaultdict(list)
    net_by_id = {n.id: n for n in nets}
    for transfer in result.transfers:
        item = net_by_id[transfer.net].item_id
        for direction, key in (("out", transfer.source), ("in", transfer.sink)):
            domain = tuple(
                p.index for p in allowed_ports(dataset, cells[key], item, direction)
            )
            domains[key, direction].extend(
                [domain] * math.ceil(transfer.rate / capacity)
            )
    try:
        for entries in domains.values():
            match_ports(entries)
    except TransportError as error:
        result.reason = str(error)
        return result
    result.feasible = True
    result.optimal = model.getModelStatus() == highspy.HighsModelStatus.kOptimal
    result.reason = "exactly reconstructed direct-port incumbent"
    return result


__all__ = [
    "DENOMINATOR",
    "MAX_EDGES",
    "SECONDS",
    "allocate",
    "duty_of",
    "endpoint_rates",
    "port_count",
]
