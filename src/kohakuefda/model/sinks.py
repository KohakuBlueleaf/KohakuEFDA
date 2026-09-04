"""Activation requirements and fluid dump sinks that recipes alone do not express."""

from fractions import Fraction

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.rates import Rate

ZONE_GAS_PER_MIN = Fraction(6)
ZONE_MACHINE = "vaporizer_1"
ZONE_SIDE = 13
SOURCE_RATES = {
    "unloader_1": Fraction(30),
    "pump_1": Fraction(60),
    "pump_2": Fraction(60),
    "gas_pump_1": Fraction(20),
}
LIQUID_PUMP = "pump_1"
GAS_PUMP = "gas_pump_1"


class Activation(EfdaModel):
    """A machine runs only while fed ``min_rate``/min of ``item_id`` (excess up to ``max_rate`` is wasted)."""

    machine_id: str
    item_id: str
    min_rate: Rate
    max_rate: Rate


class DumpSink(EfdaModel):
    """A facility that destroys fluids: which items, and how much per machine per minute."""

    machine_id: str
    items: list[str]
    rate_per_machine: Rate
    fixed: bool = False
