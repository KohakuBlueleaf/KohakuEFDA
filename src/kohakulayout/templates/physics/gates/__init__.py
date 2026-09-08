"""The gates pack: logic gates on a grid, wired like a schematic. The first instance of the framework.

Two carriers on two layers, jumpers where wires cross, free branching, edge constraints
for inputs and outputs, and an optional power field. No game in it.
"""

from typing import Any

from kohakulayout.ir import Fabric, Footprint, Netlist, Problem
from kohakulayout.physics import BasePhysics, register
from kohakulayout.templates.physics.gates.boundaries import GatesBoundaries
from kohakulayout.templates.physics.gates.carriers import GatesCarriers
from kohakulayout.templates.physics.gates.fabric import fabric
from kohakulayout.templates.physics.gates.fields import GatesFields
from kohakulayout.templates.physics.gates.library import JUMPER, LIBRARY
from kohakulayout.templates.physics.gates.objective import GatesObjective
from kohakulayout.templates.physics.gates.rules import RULES
from kohakulayout.templates.physics.gates.synth import from_expressions, random_circuit


@register
class GatesPhysics(BasePhysics):
    id = "gates"
    version = "1"

    def __init__(self) -> None:
        super().__init__()
        self.carriers = GatesCarriers()
        self.boundaries = GatesBoundaries()
        self.rules = RULES
        self.objective = GatesObjective()

    def fabric(self, params: dict[str, Any]) -> Fabric:
        return fabric(params)

    def library(self) -> dict[str, Footprint]:
        return dict(LIBRARY)

    def unit_footprints(self) -> dict[str, Footprint]:
        return {JUMPER.id: JUMPER, **super().unit_footprints()}


@register
class GatesPowerPhysics(GatesPhysics):
    """The power variant: every gate needs the ``power`` field, VDD emitters provide it."""

    id = "gates-power"

    def __init__(self) -> None:
        super().__init__()
        self.fields = GatesFields()


def problem(netlist: Netlist, power: bool = False, **params: Any) -> Problem:
    """A gates problem around a netlist; ``width`` and ``height`` size the board, ``power`` picks the variant."""
    physics = GatesPowerPhysics() if power else GatesPhysics()
    if netlist.pack != physics.id:
        netlist = netlist.model_copy(update={"pack": physics.id})
    return Problem(
        physics=physics.ref,
        fabric=physics.fabric(params),
        netlist=netlist,
        params=params,
    )


__all__ = ["LIBRARY", "GatesPhysics", "from_expressions", "problem", "random_circuit"]
