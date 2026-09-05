"""Hierarchical views over one routed state; grouping does not imply reserved rectangles."""

from dataclasses import dataclass

from kohakuefda.framework.context import Context
from kohakuefda.model.solver import Link, Scope


@dataclass(frozen=True)
class Component:
    """A member set with its internal and boundary flow connections."""

    members: frozenset[str]
    internal: tuple[Link, ...]
    boundary: tuple[Link, ...]
    occupied: frozenset[tuple[int, int]]

    def scope(self, reroute_boundary: bool = True) -> Scope:
        routes = self.internal + (self.boundary if reroute_boundary else ())
        return Scope(self.members, frozenset(link.id for link in routes))


def component(context: Context, members: frozenset[str]) -> Component:
    """Extract a revision-local component with explicit external obligations."""
    if members - context.blocks.keys():
        raise ValueError("component contains unknown machines")
    internal, boundary = [], []
    for link in context.links:
        ends = int(link.source in members) + int(link.sink in members)
        if ends == 2:
            internal.append(link)
        elif ends == 1:
            boundary.append(link)
    cells = frozenset(
        c for i, footprint in context.view.footprints if i in members for c in footprint
    )
    return Component(members, tuple(internal), tuple(boundary), cells)
