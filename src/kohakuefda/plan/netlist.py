"""Cells → netlist: one net per item joining every output pin to every input pin of that item."""

import logging
from fractions import Fraction

from kohakuefda.flow.lanes import lane_capacity
from kohakuefda.model.cells import CellInstance, Netlist, NetSpec, Pin, PinRef
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Finding, Plan
from kohakuefda.model.rates import lanes_needed
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.depot import io_budget, via_depot_ok
from kohakuefda.plan.machines import instantiate
from kohakuefda.plan.transport import allocate, materialize
from kohakuefda.plan.units import assign_units, extract

log = logging.getLogger(__name__)
BRICK_KINDS = ("unloader", "loader")
TRANSPORT = ("legacy", "rated", "direct")


def _refs(pins: list[tuple[CellInstance, Pin]], planned: Fraction) -> list[PinRef]:
    """Pins with the planned flow spread over them in proportion to their lane rates."""
    nominal = sum((p.rate for _, p in pins), Fraction(0))
    factor = planned / nominal if nominal > 0 else Fraction(0)
    return [PinRef(cell_id=c.id, pin_id=p.id, rate=p.rate * factor) for c, p in pins]


def build_nets(
    dataset: Dataset, plan: Plan, cells: list[CellInstance], rated: bool = False
) -> list[NetSpec]:
    """One net per item, and one per ``Pin.net`` key of an item, named by the item and the
    key alone so the names hold across runs; keyed nets share the item's planned flow in
    proportion to their own pins' rates; ``rated`` nets carry what their sources make.
    """
    by_key: dict[tuple[str, str | None], dict[str, list[tuple[CellInstance, Pin]]]] = {}
    for cell in cells:
        for pin in cell.pins:
            by_key.setdefault((pin.item_id, pin.net), {"in": [], "out": []})[
                pin.direction
            ].append((cell, pin))
    own = {
        key: min(
            sum((p.rate for _, p in ends["in"]), Fraction(0)),
            sum((p.rate for _, p in ends["out"]), Fraction(0)),
        )
        for key, ends in by_key.items()
    }
    keyed: dict[str, Fraction] = {}
    for (item_id, key), flow in own.items():
        if key is not None:
            keyed[item_id] = keyed.get(item_id, Fraction(0)) + flow
    nets: list[NetSpec] = []
    for (item_id, key), ends in by_key.items():
        balance = plan.items.get(item_id)
        planned = balance.produced + balance.supplied if balance else Fraction(0)
        nominal = sum((p.rate for _, p in ends["in"]), Fraction(0))
        if rated:
            made = sum((p.rate for _, p in ends["out"]), Fraction(0))
            planned = made if ends["out"] else nominal
        elif item_id in keyed:
            share = min(1, planned / keyed[item_id]) if keyed[item_id] > 0 else 0
            planned = own[item_id, key] * share if key is not None else Fraction(0)
        elif ends["out"] and all(c.kind == "entry" for c, _ in ends["out"]):
            planned = own[item_id, key]
        capacity = lane_capacity(dataset, item_id)
        net = NetSpec(
            id=f"n_{item_id}" + (f"_{key}" if key else ""),
            item_id=item_id,
            kind="pipe" if dataset.items[item_id].phase.is_fluid else "belt",
            rate=planned,
            nominal=nominal,
            trunk_lanes=lanes_needed(planned, capacity),
            sources=_refs(ends["out"], planned),
            sinks=_refs(ends["in"], planned),
            via_depot_ok=via_depot_ok(
                dataset,
                item_id,
                {c.kind for c, _ in ends["out"]},
                {c.kind for c, _ in ends["in"]},
            ),
        )
        log.debug(
            "net %s: %s/min over %d trunk lane(s), %d source(s), %d sink(s)",
            net.id,
            net.rate,
            net.trunk_lanes,
            len(net.sources),
            len(net.sinks),
        )
        nets.append(net)
    return nets


def brick_count(cells: list[CellInstance]) -> int:
    """Depot bricks outside the core."""
    return sum(1 for c in cells if c.kind in BRICK_KINDS)


def netlist_findings(
    dataset: Dataset,
    scenario: Scenario,
    plan: Plan,
    cells: list[CellInstance],
    nets: list[NetSpec],
) -> list[Finding]:
    out: list[Finding] = []
    for net in nets:
        if net.rate > 0 and (not net.sources or not net.sinks):
            side = "source" if not net.sources else "sink"
            out.append(
                Finding(
                    rule="netlist.open",
                    severity="error",
                    subject=net.id,
                    message=f"{dataset.items[net.item_id].names.en} flows {net.rate}/min but has no {side} pin",
                )
            )
        if net.nominal < net.rate:
            out.append(
                Finding(
                    rule="netlist.short",
                    severity="error",
                    subject=net.id,
                    message=f"sink lanes take {net.nominal}/min, the plan needs {net.rate}/min",
                )
            )
    bricks = brick_count(cells)
    budget = io_budget(dataset, scenario.basement)
    if budget is not None and bricks > budget:
        out.append(
            Finding(
                rule="netlist.io_slots",
                severity="error",
                subject="depot",
                message=f"{bricks} depot bricks exceed the {budget} the depot level offers; raise the depot level or route through fewer lanes",
            )
        )
    parts = [c for c in cells if c.kind == "depot"]
    if parts:
        out.append(
            Finding(
                rule="netlist.bus",
                severity="info",
                subject="depot",
                message=f"a Depot Bus of {len(parts)} part(s) seats {bricks} brick(s); the parts and bricks touch in any arrangement",
            )
        )
    zones = [c for c in cells if c.kind == "zone"]
    if zones:
        planned = sum(plan.zones.values())
        out.append(
            Finding(
                rule="netlist.zones",
                severity="warning" if len(zones) > planned else "info",
                subject="zones",
                message=(
                    f"{len(zones)} gas zone(s), each a Gas Dispersing Unit whose 13×13 must contain its machines"
                    + (
                        f"; the plan counted {planned}, the machines' footprints need more"
                        if len(zones) > planned
                        else ""
                    )
                ),
            )
        )
    entries = [c for c in cells if c.kind == "entry"]
    if entries:
        names = sorted({dataset.items[c.pins[0].item_id].names.en for c in entries})
        out.append(
            Finding(
                rule="netlist.entries",
                severity="info",
                subject="entries",
                message=f"{len(entries)} outside input(s) piped in at the area's border: {', '.join(names)}",
            )
        )
    for f in out:
        level = {"error": log.error, "warning": log.warning}.get(f.severity, log.info)
        level(f.message, rule=f.rule, subject=f.subject)
    return out


def build_netlist(
    dataset: Dataset, scenario: Scenario, plan: Plan, transport: str = TRANSPORT[0]
) -> Netlist:
    """The plan's cells and nets under a ``TRANSPORT`` policy: ``legacy`` nominal
    machines, ``rated`` exact operating points, ``direct`` the rated netlist re-laned by
    the transport allocator (the rated one kept, with a warning, when it finds none)."""
    if transport not in TRANSPORT:
        raise ValueError(f"transport must be one of {TRANSPORT}")

    rated = transport != "legacy"
    hierarchy = extract(dataset, plan)
    cells, links = instantiate(dataset, scenario, plan, hierarchy, rated=rated)
    assign_units(hierarchy, cells)
    nets = build_nets(dataset, plan, cells, rated=rated)
    log.info(
        "netlist built: %d cell(s), %d net(s), %d brick(s)",
        len(cells),
        len(nets),
        brick_count(cells),
    )
    netlist = Netlist(
        dataset_version=dataset.version.id,
        scenario=scenario,
        plan_status=plan.status,
        cells=cells,
        nets=nets,
        links=links,
        findings=netlist_findings(dataset, scenario, plan, cells, nets),
    )
    if transport != "direct":
        return netlist

    allocation = allocate(dataset, netlist)
    if allocation.feasible:
        return materialize(dataset, netlist, allocation)
    netlist.findings.append(
        Finding(
            rule="transport.direct",
            severity="warning",
            subject="transport",
            message=f"no direct transport allocation ({allocation.reason}); the rated netlist stands",
        )
    )
    return netlist
