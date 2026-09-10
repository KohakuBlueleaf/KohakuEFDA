"""Stage 1 for Endfield: belts and pipes cross through bridges, branch through splitters and convergers.

A wire shares a cell only with a unit of its own carrier, which is itself a cell of the
network (LOG-11). Belts bridge belts and pipes bridge pipes (JCT-04); there is no
side-loading, so every branch is a splitter and every merge a converger (LOG-07, JCT-01,
JCT-02); a continuous belt runs at most 110 cells and a pipe 80 (LOG-05).
"""

from kohakuefda.physics.library import (
    BRIDGE,
    CARRIERS,
    CONVERGER,
    RUN_LIMIT,
    SPLITTER,
    UNIT_CARRIER,
    UNITS,
)
from kohakulayout.ir import Footprint
from kohakulayout.physics import (
    CrossingRule,
    DefaultCarriers,
    JunctionRule,
    Occupant,
)

BENT_CROSSINGS: bool = False
"""Whether a lane may start on a cell where the crossed belt or pipe bends; off, as JCT-04 makes a bridge two straight paths."""


class EndfieldCarriers(DefaultCarriers):
    def may_share(self, a: Occupant, b: Occupant) -> bool:
        wire, other = (a, b) if a.kind == "wire" else (b, a)
        return (
            wire.kind == "wire"
            and other.kind == "unit"
            and UNIT_CARRIER.get(other.unit_kind or "") == wire.carrier
        )

    def crossing(self, a: str, b: str) -> CrossingRule:
        if a == b and a in CARRIERS:
            return CrossingRule(mode="unit", unit=UNITS[BRIDGE[a]], bent=BENT_CROSSINGS)
        return CrossingRule(mode="forbidden")

    def junction(self, carrier: str) -> JunctionRule:
        if carrier not in CARRIERS:
            return JunctionRule(mode="forbidden")
        return JunctionRule(
            mode="unit", split=UNITS[SPLITTER[carrier]], merge=UNITS[CONVERGER[carrier]]
        )

    def run_limit(self, carrier: str) -> int | None:
        return RUN_LIMIT.get(carrier)

    def repeater(self, carrier: str) -> Footprint | None:
        """A splitter ends one continuous conveyor and starts the next (LOG-05)."""
        if carrier not in CARRIERS:
            return None
        return UNITS[SPLITTER[carrier]]

    def transfers_through(self, unit_kind: str, carrier: str) -> bool:
        return UNIT_CARRIER.get(unit_kind) == carrier


__all__ = ["EndfieldCarriers"]
