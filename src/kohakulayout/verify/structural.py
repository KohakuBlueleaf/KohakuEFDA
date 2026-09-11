"""Structural findings: the layout against the netlist and the fabric, with no physics asked."""

from typing import Any

from kohakulayout.ir import Finding, Layout

GEOMETRY = "kl.geometry"
MISSING = "kl.missing"
UNROUTED = "kl.unrouted"


def geometry(layout: Layout, netlist: Any, fabric: Any) -> tuple[Finding, ...]:
    """Every ``Layout.check`` and ``Layout.check_against`` message as an error finding."""
    return tuple(
        Finding(
            rule=GEOMETRY,
            severity="error",
            subject=message.split(":", 1)[0],
            message=message,
        )
        for message in (*layout.check(), *layout.check_against(netlist, fabric))
    )


def missing(layout: Layout, netlist: Any) -> tuple[Finding, ...]:
    flat = netlist.flatten()
    placed = set(layout.flatten(netlist).placements)
    return tuple(
        Finding(
            rule=MISSING,
            severity="error",
            subject=f"cell:{cell_id}",
            message=f"{cell_id} is not placed",
        )
        for cell_id in sorted(flat.cells)
        if cell_id not in placed
    )


def unrouted(layout: Layout, netlist: Any) -> tuple[Finding, ...]:
    flat = netlist.flatten()
    wired = set(layout.flatten(netlist).wires)
    return tuple(
        Finding(
            rule=UNROUTED,
            severity="error",
            subject=f"net:{net_id}",
            message=f"{net_id} is not routed",
        )
        for net_id in sorted(flat.nets)
        if net_id not in wired
    )


def structural(layout: Layout, netlist: Any, fabric: Any = None) -> tuple[Finding, ...]:
    return (
        geometry(layout, netlist, fabric)
        + missing(layout, netlist)
        + unrouted(layout, netlist)
    )


__all__ = [
    "GEOMETRY",
    "MISSING",
    "UNROUTED",
    "geometry",
    "missing",
    "structural",
    "unrouted",
]
