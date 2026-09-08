"""Balance findings: what a net supplies against what its sinks demand, and what its carrier can carry."""

from collections.abc import Mapping
from fractions import Fraction

from kohakulayout.ir import Fabric, Finding, Netlist

STARVED = "kl.balance.starved"
SURPLUS = "kl.balance.surplus"
UNFED = "kl.balance.unfed"
CAPACITY = "kl.balance.capacity"


def balance(
    nl: Netlist,
    demand: Mapping[str, Fraction | int] | None = None,
    fabric: Fabric | None = None,
) -> tuple[Finding, ...]:
    """Per net: unfed (sinks, no source, no edge), starved, surplus against ``demand`` per sink cell, over capacity."""
    demand = demand or {}
    out: list[Finding] = []
    for net in nl.nets.values():
        subject = f"net:{net.id}"
        if net.sinks and not net.sources and net.outside is None:
            out.append(
                Finding(
                    rule=UNFED,
                    severity="error",
                    subject=subject,
                    message=f"{net.id} has sinks and nothing feeds it",
                )
            )
        needs = sum(
            (Fraction(demand[r.cell]) for r in net.sinks if r.cell in demand),
            Fraction(0),
        )
        if needs and net.rate < needs:
            out.append(
                Finding(
                    rule=STARVED,
                    severity="warning",
                    subject=subject,
                    message=f"{net.id} supplies {net.rate} against a demand of {needs}",
                )
            )
        elif needs and net.rate > needs:
            out.append(
                Finding(
                    rule=SURPLUS,
                    severity="info",
                    subject=subject,
                    message=f"{net.id} supplies {net.rate} against a demand of {needs}",
                )
            )
        carrier = fabric.carriers.get(net.carrier) if fabric is not None else None
        if (
            carrier is not None
            and carrier.capacity is not None
            and net.rate > carrier.capacity
        ):
            out.append(
                Finding(
                    rule=CAPACITY,
                    severity="error",
                    subject=subject,
                    message=f"{net.id} carries {net.rate} over a capacity of {carrier.capacity}",
                )
            )
    return tuple(out)


__all__ = ["CAPACITY", "STARVED", "SURPLUS", "UNFED", "balance"]
