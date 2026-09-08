"""Stage 1 defaults: exclusive cells, no crossings, no junctions, no run limits."""

from kohakulayout.ir import Footprint
from kohakulayout.physics.protocol import CrossingRule, JunctionRule, Occupant


class DefaultCarriers:
    """Every carrier rule at its most restrictive: a pack relaxes what its game allows."""

    def may_share(self, a: Occupant, b: Occupant) -> bool:
        return False

    def crossing(self, a: str, b: str) -> CrossingRule:
        return CrossingRule(mode="forbidden")

    def junction(self, carrier: str) -> JunctionRule:
        return JunctionRule(mode="forbidden")

    def run_limit(self, carrier: str) -> int | None:
        return None

    def repeater(self, carrier: str) -> Footprint | None:
        return None

    def transfers_through(self, unit_kind: str, carrier: str) -> bool:
        return False
