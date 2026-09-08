"""Stage 1 for gates: wires cross through a jumper, carriers share across layers, branching is free."""

from kohakulayout.ir import Footprint
from kohakulayout.physics import CrossingRule, DefaultCarriers, JunctionRule, Occupant
from kohakulayout.templates.physics.gates.library import JUMPER


class GatesCarriers(DefaultCarriers):
    def may_share(self, a: Occupant, b: Occupant) -> bool:
        if a.kind == "wire" and b.kind == "wire":
            return a.carrier != b.carrier
        wire, other = (a, b) if a.kind == "wire" else (b, a)
        return (
            wire.kind == "wire"
            and other.kind == "unit"
            and other.unit_kind == JUMPER.id
        )

    def crossing(self, a: str, b: str) -> CrossingRule:
        if a == b == "wire":
            return CrossingRule(mode="unit", unit=JUMPER)
        if a == b:
            return CrossingRule(mode="forbidden")
        return CrossingRule(mode="free")

    def junction(self, carrier: str) -> JunctionRule:
        return JunctionRule(mode="free")

    def repeater(self, carrier: str) -> Footprint | None:
        return None

    def transfers_through(self, unit_kind: str, carrier: str) -> bool:
        return unit_kind == JUMPER.id and carrier == "wire"


__all__ = ["GatesCarriers"]
