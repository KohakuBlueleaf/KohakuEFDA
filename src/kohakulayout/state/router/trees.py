"""Trees: one net with many terminals grown nearest-first, junctions per the pack's rule."""

from dataclasses import dataclass, field
from typing import Any

from kohakulayout.ir import Refusal, Segment
from kohakulayout.ir.geometry import XY
from kohakulayout.state.router.pathfinder import Search, find, occluded_free
from kohakulayout.state.router.protocol import Terminal, refuse, terminals


@dataclass
class Plan:
    """What a routed net will become, before anything is written to the world."""

    net_id: str
    segments: list[Segment] = field(default_factory=list)
    crossings: list[tuple[XY, str, bool]] = field(default_factory=list)
    junctions: list[tuple[XY, str]] = field(default_factory=list)
    rips: set[str] = field(default_factory=set)
    cost: int = 0


def may_join(world: Any, rule: Any, cell: XY) -> bool:
    """Whether a junction unit could stand on this tree cell: the layers it occludes are free there."""
    if rule.mode != "unit":
        return True
    return all(
        fp is None or occluded_free(world, fp, cell) for fp in (rule.split, rule.merge)
    )


def grow(world: Any, net: Any, search: Search) -> Plan | Refusal:
    """A plan connecting every terminal of ``net``: the sources join first into a trunk, then the sinks branch from the last join or from one another, so every cell carries flow one way."""
    found = terminals(world, net)
    if isinstance(found, Refusal):
        return found
    edge = world.physics.boundaries.outside(world, net)
    if not found and not edge:
        return refuse(net.id, "no terminals")
    rule = world.physics.carriers.junction(net.carrier)
    groups: list[tuple[frozenset[XY], Terminal | None]] = [
        (frozenset({t.cell}), t) for t in found
    ]
    if edge:
        groups.append((frozenset(edge), None))
    if rule.mode == "forbidden" and len(groups) > 2:
        return refuse(
            net.id,
            f"{len(groups)} terminals need a junction, which {net.carrier!r} forbids",
        )
    root_cells, _ = groups[0]
    tree: set[XY] = set(root_cells)
    plan = Plan(net_id=net.id)
    degree: dict[XY, int] = dict.fromkeys(root_cells, 0)
    trunk: set[XY] = set(root_cells)
    branches: set[XY] = set()
    for _ in range(len(groups) - 1):
        remaining = [g for g in groups[1:] if not (g[0] & tree)]
        if not remaining:
            break
        sources = [g for g in remaining if g[1] is None or g[1].direction == "out"]
        targets = frozenset().union(*(g[0] for g in (sources or remaining)))
        starts = tree if sources else (trunk | branches)
        joinable = frozenset(
            c for c in starts if degree.get(c, 0) == 0 or may_join(world, rule, c)
        )
        origins = joinable or frozenset(starts)
        path = find(search, origins, targets, frozenset(tree) - origins)
        if path is None:
            return refuse(
                net.id,
                f"no path from {min(origins)} to any of {sorted(targets)[:4]}",
            )
        join = path.cells[0]
        reached = next(g for g in remaining if path.cells[-1] in g[0])
        mode = (
            "merge"
            if reached[1] is not None and reached[1].direction == "out"
            else "split"
        )
        if len(path.cells) > 1 and degree.get(join, 0) >= 1:
            plan.junctions.append((join, mode))
        for cell in path.cells:
            degree[cell] = degree.get(cell, 0) + 1
        tree.update(path.cells)
        if sources:
            trunk = {join}
        else:
            branches.update(path.cells)
        plan.segments.append(
            Segment(carrier=net.carrier, layer=search.layer, cells=path.cells)
        )
        plan.crossings.extend(path.crossings)
        plan.rips |= path.rips
        plan.cost += path.cost
    if not plan.segments:
        only = min(root_cells)
        plan.segments.append(
            Segment(carrier=net.carrier, layer=search.layer, cells=(only,))
        )
    return plan


__all__ = ["Plan", "grow"]
