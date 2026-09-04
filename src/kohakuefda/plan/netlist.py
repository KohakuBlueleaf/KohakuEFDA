"""Cells → netlist: one net per item joining every output pin to every input pin of that item."""

import logging
from fractions import Fraction

from kohakuefda.flow.lanes import lane_capacity
from kohakuefda.layout.depot_via import io_budget, via_depot_ok
from kohakuefda.model.cells import CellInstance, Netlist, NetSpec, Pin, PinRef
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Finding, Plan
from kohakuefda.model.rates import lanes_needed
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.machines import instantiate

log = logging.getLogger(__name__)
BRICK_KINDS = ("unloader", "loader")


def _refs(pins: list[tuple[CellInstance, Pin]], planned: Fraction) -> list[PinRef]:
    """Pins with the planned flow spread over them in proportion to their lane rates."""
    nominal = sum((p.rate for _, p in pins), Fraction(0))
    factor = planned / nominal if nominal > 0 else Fraction(0)
    return [PinRef(cell_id=c.id, pin_id=p.id, rate=p.rate * factor) for c, p in pins]


def build_nets(
    dataset: Dataset, plan: Plan, cells: list[CellInstance]
) -> list[NetSpec]:
    by_item: dict[str, dict[str, list[tuple[CellInstance, Pin]]]] = {}
    for cell in cells:
        for pin in cell.pins:
            by_item.setdefault(pin.item_id, {"in": [], "out": []})[
                pin.direction
            ].append((cell, pin))
    nets: list[NetSpec] = []
    for index, (item_id, ends) in enumerate(by_item.items()):
        balance = plan.items.get(item_id)
        planned = balance.produced + balance.supplied if balance else Fraction(0)
        nominal = sum((p.rate for _, p in ends["in"]), Fraction(0))
        if ends["out"] and all(c.kind == "entry" for c, _ in ends["out"]):
            planned = min(nominal, sum((p.rate for _, p in ends["out"]), Fraction(0)))
        capacity = lane_capacity(dataset, item_id)
        net = NetSpec(
            id=f"n{index}_{item_id}",
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


def build_netlist(dataset: Dataset, scenario: Scenario, plan: Plan) -> Netlist:
    cells = instantiate(dataset, scenario, plan)
    nets = build_nets(dataset, plan, cells)
    bricks = brick_count(cells)
    log.info(
        "netlist built: %d cell(s), %d net(s), %d brick(s)",
        len(cells),
        len(nets),
        bricks,
    )
    return Netlist(
        dataset_version=dataset.version.id,
        scenario=scenario,
        plan_status=plan.status,
        cells=cells,
        nets=nets,
        findings=netlist_findings(dataset, scenario, plan, cells, nets),
    )
