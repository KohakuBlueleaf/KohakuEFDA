"""Nets: item flows from producers to consumers, split proportionally, with lane counts."""

import logging
from fractions import Fraction

from kohakuefda.flow.lanes import lane_capacity, lanes_for
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import ItemBalance, Net, RecipeUse

log = logging.getLogger(__name__)
SUPPLY = "supply"
TARGET = "target"


def _producers(
    dataset: Dataset, item_id: str, uses: list[RecipeUse], balance: ItemBalance
) -> list[tuple[str, Fraction]]:
    out: list[tuple[str, Fraction]] = []
    for use in uses:
        rate = dataset.recipes[use.recipe_id].output_rate(item_id) * use.machines_exact
        if rate > 0:
            out.append((use.recipe_id, rate))
    if balance.supplied > 0:
        out.append((SUPPLY, balance.supplied))
    return out


def _consumers(
    dataset: Dataset,
    item_id: str,
    uses: list[RecipeUse],
    balance: ItemBalance,
    activation_mode: str,
) -> list[tuple[str, Fraction]]:
    out: list[tuple[str, Fraction]] = []
    for use in uses:
        recipe = dataset.recipes[use.recipe_id]
        rate = recipe.input_rate(item_id) * use.machines_exact
        activation = dataset.activations.get(use.machine_id)
        if activation and activation.item_id == item_id:
            count = use.machines_exact if activation_mode == "duty" else use.machines
            rate += activation.min_rate * count
        if rate > 0:
            out.append((use.recipe_id, rate))
    if balance.delivered > 0:
        out.append((TARGET, balance.delivered))
    if balance.sunk > 0:
        out.append((balance.sink_kind or "sink", balance.sunk))
    return out


def build_nets(
    dataset: Dataset,
    uses: list[RecipeUse],
    items: dict[str, ItemBalance],
    activation_mode: str = "built",
) -> list[Net]:
    """One net per (item, producer, consumer) pair with a positive proportional share."""
    nets: list[Net] = []
    for item_id, balance in items.items():
        producers = _producers(dataset, item_id, uses, balance)
        consumers = _consumers(dataset, item_id, uses, balance, activation_mode)
        total = sum((rate for _, rate in producers), Fraction(0))
        if total <= 0:
            continue
        fluid = dataset.items[item_id].phase.is_fluid
        capacity = lane_capacity(dataset, item_id)
        for consumer, demand in consumers:
            for producer, output in producers:
                share = demand * output / total
                if share <= 0:
                    continue
                net = Net(
                    item_id=item_id,
                    source=producer,
                    target=consumer,
                    rate=share,
                    fluid=fluid,
                    lanes=lanes_for(dataset, item_id, share),
                    lane_capacity=capacity,
                )
                log.debug(
                    "net %s: %s -> %s, %s/min, %d lane(s)",
                    item_id,
                    producer,
                    consumer,
                    share,
                    net.lanes,
                )
                nets.append(net)
    return nets
