"""The null pack: every default, a grid from params, and a tiny library with no game in it.

An instrument, not a template to copy: with the in-order solver it measures what a
placement costs before any game and any strategy.
"""

from typing import Any

from kohakulayout.ir import (
    Carrier,
    Cell,
    Fabric,
    Footprint,
    Net,
    Netlist,
    PinRef,
    Port,
    Problem,
    Region,
)
from kohakulayout.physics import BasePhysics, register

LIBRARY: dict[str, Footprint] = {
    "CELL": Footprint(id="CELL", width=1, height=1),
    "BOX": Footprint(id="BOX", width=2, height=2, rotations=(0,)),
    "TAP": Footprint(
        id="TAP",
        width=1,
        height=1,
        ports=(Port(id="y", side="E", offset=0, direction="out", carrier="wire"),),
    ),
    "SINK": Footprint(
        id="SINK",
        width=1,
        height=1,
        ports=(Port(id="a", side="W", offset=0, direction="in", carrier="wire"),),
    ),
}


@register
class NullPhysics(BasePhysics):
    id = "null"
    version = "1"

    def fabric(self, params: dict[str, Any]) -> Fabric:
        width = int(params.get("width", 16))
        height = int(params.get("height", 16))
        every = frozenset((x, y) for y in range(height) for x in range(width))
        return Fabric(
            width=width,
            height=height,
            layers=("ground",),
            carriers={"wire": Carrier(id="wire", layer="ground")},
            regions={"build": Region.of("build", every)},
        )

    def library(self) -> dict[str, Footprint]:
        return dict(LIBRARY)


def problem(width: int = 8, height: int = 8, taps: int = 1) -> Problem:
    """The null instance: ``taps`` TAP cells each wired to its own SINK, plus one BOX and one CELL."""
    physics = NullPhysics()
    cells = {
        "box": Cell(id="box", kind="BOX", footprint="BOX"),
        "c": Cell(id="c", kind="CELL", footprint="CELL"),
    }
    nets = {}
    for i in range(1, taps + 1):
        cells[f"t{i}"] = Cell(id=f"t{i}", kind="TAP", footprint="TAP")
        cells[f"s{i}"] = Cell(id=f"s{i}", kind="SINK", footprint="SINK")
        nets[f"n{i}"] = Net(
            id=f"n{i}",
            carrier="wire",
            sources=(PinRef(cell=f"t{i}", pin="y"),),
            sinks=(PinRef(cell=f"s{i}", pin="a"),),
        )
    netlist = Netlist(pack="null", library=dict(LIBRARY), cells=cells, nets=nets)
    params = {"width": width, "height": height}
    return Problem(
        physics=physics.ref,
        fabric=physics.fabric(params),
        netlist=netlist,
        params=params,
    )


__all__ = ["LIBRARY", "NullPhysics", "problem"]
