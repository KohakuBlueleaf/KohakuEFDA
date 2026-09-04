"""Lane sizing: how many belts or pipes a flow needs, and how many machines one lane feeds."""

import logging
from fractions import Fraction
from typing import NamedTuple

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.rates import lanes_needed
from kohakuefda.model.recipes import Recipe

log = logging.getLogger(__name__)


class LaneSplit(NamedTuple):
    """One machine's flow of an item over ports: how many ports, the rate per port, machines per lane."""

    ports: int
    per_port: Fraction
    per_lane: int


def lane_capacity(dataset: Dataset, item_id: str) -> Fraction:
    """Belt rate for solids, pipe rate for fluids."""
    if dataset.items[item_id].phase.is_fluid:
        return dataset.constants.pipe_per_min
    return dataset.constants.belt_per_min


def lanes_for(dataset: Dataset, item_id: str, rate: Fraction) -> int:
    return lanes_needed(rate, lane_capacity(dataset, item_id))


def lane_split(rate: Fraction, capacity: Fraction) -> LaneSplit:
    """Spread a per-machine rate over the fewest ports that each stay within one lane."""
    if rate <= 0:
        return LaneSplit(0, Fraction(0), 0)
    ports = lanes_needed(rate, capacity)
    per_port = rate / ports
    return LaneSplit(ports, per_port, int(capacity // per_port))


def machines_per_lane(dataset: Dataset, recipe: Recipe, item_id: str) -> int:
    """How many machines running ``recipe`` one full lane of ``item_id`` can feed."""
    per_machine = recipe.input_rate(item_id)
    if per_machine <= 0:
        return 0
    count = int(lane_capacity(dataset, item_id) // per_machine)
    log.debug("%s: one lane of %s feeds %d machine(s)", recipe.id, item_id, count)
    return count
