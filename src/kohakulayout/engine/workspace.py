"""A workspace: an oversized board with the target region in its middle, and the way back onto the target."""

from typing import Any

from kohakulayout.ir import (
    Layout,
    Placement,
    Problem,
    Rect,
    Reservation,
    Segment,
    Unit,
    Wire,
)
from kohakulayout.ir.geometry import XY, footprint_cells


class Workspace:
    def __init__(self, problem: Problem, physics: Any, scale: int = 2) -> None:
        self.origin_problem = problem
        width, height = problem.fabric.width, problem.fabric.height
        params = {**problem.params, "width": width * scale, "height": height * scale}
        self.problem = problem.model_copy(
            update={"fabric": physics.fabric(params), "params": params}
        )
        ox, oy = (width * scale - width) // 2, (height * scale - height) // 2
        self.target = Rect(x=ox, y=oy, w=width, h=height)
        self.target_cells: frozenset[XY] = self.target.cells()

    def shift(self, xy: XY, back: bool = True) -> XY:
        sign = -1 if back else 1
        return (xy[0] + sign * self.target.x, xy[1] + sign * self.target.y)

    def overflow(self, layout: Layout) -> int:
        """Cells of placements, wires and units outside the target."""
        netlist = self.problem.netlist.flatten()
        cells: set[XY] = set()
        for key, placement in layout.placements.items():
            fp = netlist.footprint_for(key)
            if fp is not None:
                cells.update(
                    footprint_cells(
                        placement.x, placement.y, fp.width, fp.height, placement.rot
                    )
                )
        for wire in layout.wires.values():
            cells.update(wire.cells())
        for unit in layout.units.values():
            cells.add((unit.x, unit.y))
        return sum(1 for c in cells if c not in self.target_cells)

    def project(self, layout: Layout) -> Layout:
        """The layout translated onto the target's origin; cells outside it land off the grid."""
        placements = {
            k: Placement(
                cell=p.cell, x=p.x - self.target.x, y=p.y - self.target.y, rot=p.rot
            )
            for k, p in layout.placements.items()
        }
        wires = {
            k: Wire(
                net=w.net,
                segments=tuple(
                    Segment(
                        carrier=s.carrier,
                        layer=s.layer,
                        cells=tuple(self.shift(c) for c in s.cells),
                    )
                    for s in w.segments
                ),
                units=w.units,
                ports=w.ports,
            )
            for k, w in layout.wires.items()
        }
        units = {
            k: Unit(
                id=u.id,
                kind=u.kind,
                footprint=u.footprint,
                x=u.x - self.target.x,
                y=u.y - self.target.y,
                rot=u.rot,
                owner=u.owner,
                attrs=u.attrs,
            )
            for k, u in layout.units.items()
        }
        reservations = tuple(
            Reservation(
                tag=r.tag,
                layer=r.layer,
                cells=tuple(self.shift(c) for c in r.cells),
                carrier=r.carrier,
            )
            for r in layout.reservations
        )
        return Layout(
            problem=self.origin_problem.digest(),
            placements=placements,
            wires=wires,
            units=units,
            reservations=reservations,
            attrs=layout.attrs,
        )

    def publish(self, layout: Layout) -> Layout | None:
        """The projected layout when nothing overflows; None otherwise."""
        return self.project(layout) if self.overflow(layout) == 0 else None


__all__ = ["Workspace"]
