"""Rich tables for plans and netlists."""

import logging

from rich.console import Group
from rich.table import Table

from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.names import Lang
from kohakuefda.model.plan import Finding, Plan

log = logging.getLogger(__name__)
SEVERITY_STYLE = {"info": "cyan", "warning": "yellow", "error": "red"}


def _item(dataset: Dataset, item_id: str, lang: Lang) -> str:
    item = dataset.items.get(item_id)
    return item.names.get(lang) if item else item_id


def _machine(dataset: Dataset, machine_id: str, lang: Lang) -> str:
    machine = dataset.machines.get(machine_id)
    return machine.names.get(lang) if machine else machine_id


def targets_table(plan: Plan, dataset: Dataset, lang: Lang) -> Table:
    table = Table(title=f"targets ({plan.status}, scale {plan.scale})")
    for col in ("item", "goal", "requested /min", "achieved /min"):
        table.add_column(col)
    for t in plan.targets:
        table.add_row(
            _item(dataset, t.item_id, lang),
            t.goal or "rate",
            str(t.requested),
            str(t.achieved),
        )
    return table


def recipes_table(plan: Plan, dataset: Dataset, lang: Lang) -> Table:
    table = Table(
        title=f"machines: {plan.machine_count}, power {plan.power}, footprint {plan.footprint_cells} cells"
    )
    for col in ("recipe", "machine", "mode", "crafts /min", "machines (exact)"):
        table.add_column(col)
    for use in plan.recipes:
        recipe = dataset.recipes.get(use.recipe_id)
        name = recipe.names.get(lang) if recipe else use.recipe_id
        table.add_row(
            name,
            _machine(dataset, use.machine_id, lang),
            use.mode,
            str(use.crafts_per_min),
            f"{use.machines} ({use.machines_exact})",
        )
    return table


def items_table(plan: Plan, dataset: Dataset, lang: Lang) -> Table:
    table = Table(title="item balances (/min)")
    for col in ("item", "produced", "consumed", "supplied", "delivered", "sunk", "net"):
        table.add_column(col)
    for b in plan.items.values():
        sunk = f"{b.sunk} → {b.sink_kind}" if b.sunk else "0"
        table.add_row(
            _item(dataset, b.item_id, lang),
            str(b.produced),
            str(b.consumed),
            str(b.supplied),
            str(b.delivered),
            sunk,
            str(b.net),
        )
    return table


def nets_table(plan: Plan, dataset: Dataset, lang: Lang) -> Table:
    table = Table(title="nets and lanes")
    for col in ("item", "from", "to", "rate /min", "lanes"):
        table.add_column(col)
    for net in plan.nets:
        kind = "pipe" if net.fluid else "belt"
        table.add_row(
            _item(dataset, net.item_id, lang),
            _endpoint(dataset, net.source, lang),
            _endpoint(dataset, net.target, lang),
            str(net.rate),
            f"{net.lanes} {kind}",
        )
    return table


def _endpoint(dataset: Dataset, name: str, lang: Lang) -> str:
    recipe = dataset.recipes.get(name)
    return recipe.names.get(lang) if recipe else name


def findings_table(findings: list[Finding], title: str = "findings") -> Table:
    table = Table(title=title)
    for col in ("severity", "rule", "subject", "message"):
        table.add_column(col)
    for f in findings:
        table.add_row(
            f"[{SEVERITY_STYLE[f.severity]}]{f.severity}[/]",
            f.rule,
            f.subject,
            f.message,
        )
    return table


def plan_report(plan: Plan, dataset: Dataset, lang: Lang) -> Group:
    log.debug("rendering plan report in %s", lang)
    return Group(
        targets_table(plan, dataset, lang),
        recipes_table(plan, dataset, lang),
        items_table(plan, dataset, lang),
        nets_table(plan, dataset, lang),
        findings_table(plan.findings),
    )


def _pins(
    dataset: Dataset, netlist: Netlist, cell_id: str, direction: str, lang: Lang
) -> str:
    cell = netlist.cell(cell_id)
    return ", ".join(
        f"{_item(dataset, p.item_id, lang)} {p.rate}/{p.kind}"
        for p in cell.pins_of(direction)
    )


def cells_table(netlist: Netlist, dataset: Dataset, lang: Lang) -> Table:
    total = sum(c.area for c in netlist.cells)
    table = Table(title=f"cells: {len(netlist.cells)}, {total} cells of area")
    for col in ("cell", "kind", "machine", "group", "size", "inputs", "outputs"):
        table.add_column(col)
    for cell in netlist.cells:
        table.add_row(
            cell.id,
            cell.kind + (f" ({cell.env})" if cell.env else ""),
            _machine(dataset, cell.machine_id, lang),
            cell.group or "",
            f"{cell.width}×{cell.height}",
            _pins(dataset, netlist, cell.id, "in", lang),
            _pins(dataset, netlist, cell.id, "out", lang),
        )
    return table


def netlist_nets_table(netlist: Netlist, dataset: Dataset, lang: Lang) -> Table:
    table = Table(title="nets")
    for col in (
        "net",
        "item",
        "kind",
        "rate /min",
        "sink lanes /min",
        "trunk",
        "sources",
        "sinks",
        "via depot",
    ):
        table.add_column(col)
    for net in netlist.nets:
        table.add_row(
            net.id,
            _item(dataset, net.item_id, lang),
            net.kind,
            str(net.rate),
            str(net.nominal),
            str(net.trunk_lanes),
            ", ".join(f"{r.cell_id}.{r.pin_id}" for r in net.sources),
            ", ".join(f"{r.cell_id}.{r.pin_id}" for r in net.sinks),
            "ok" if net.via_depot_ok else "",
        )
    return table


def netlist_report(netlist: Netlist, dataset: Dataset, lang: Lang) -> Group:
    log.debug("rendering netlist report in %s", lang)
    return Group(
        cells_table(netlist, dataset, lang),
        netlist_nets_table(netlist, dataset, lang),
        findings_table(netlist.findings),
    )
