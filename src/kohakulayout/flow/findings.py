"""What the evaluator reports: starvation, capacity, primed loops, and a fixed point it could not reach."""

from fractions import Fraction

from kohakulayout.ir import Finding
from kohakulayout.ir.base import rate_text

STARVED = "kl.flow.starved"
CAPACITY = "kl.flow.capacity"
LOOP = "kl.flow.loop"
UNSTABLE = "kl.flow.unstable"


def starved(pin: str, delivered: Fraction, demand: Fraction) -> Finding:
    return Finding(
        rule=STARVED,
        severity="warning",
        subject=f"pin:{pin}",
        message=f"{pin} receives {rate_text(delivered)} of the {rate_text(demand)} it wants",
    )


def capacity(net_id: str, supply: Fraction, limit: Fraction) -> Finding:
    return Finding(
        rule=CAPACITY,
        severity="warning",
        subject=f"net:{net_id}",
        message=f"{net_id} is offered {rate_text(supply)} over a capacity of {rate_text(limit)}",
    )


def loop(nets: tuple[str, ...]) -> Finding:
    return Finding(
        rule=LOOP,
        severity="info",
        subject="nets:" + ",".join(nets),
        message=f"{len(nets)} net(s) on a cycle were primed with their declared rates",
    )


def unstable(rounds: int) -> Finding:
    return Finding(
        rule=UNSTABLE,
        severity="error",
        subject="flow",
        message=f"no fixed point after {rounds} rounds",
    )


__all__ = [
    "CAPACITY",
    "LOOP",
    "STARVED",
    "UNSTABLE",
    "capacity",
    "loop",
    "starved",
    "unstable",
]
