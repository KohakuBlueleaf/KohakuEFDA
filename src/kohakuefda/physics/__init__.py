"""The Endfield physics pack: what the Core AIC Area grid means, stated to KohakuLayout.

The pack takes no dataset. Everything a scenario brings travels in the problem: the
footprints in the netlist's library, the basement in the fabric and its params, the
machine facts in ``attrs["endfield"]``. Every rule cites `.internal/game-knowledge/`.
"""

from typing import Any

from kohakuefda.physics.boundaries import EndfieldBoundaries
from kohakuefda.physics.carriers import EndfieldCarriers
from kohakuefda.physics.fabric import NAMESPACE, fabric
from kohakuefda.physics.fields import EndfieldFields
from kohakuefda.physics.flow import EndfieldFlow
from kohakuefda.physics.library import PYLON_FOOTPRINT, UNITS
from kohakuefda.physics.objective import EndfieldObjective
from kohakuefda.physics.rules import RULES
from kohakulayout.ir import Fabric, Footprint
from kohakulayout.physics import BasePhysics, register

PACK = "endfield"
VERSION = "1"


@register
class EndfieldPhysics(BasePhysics):
    id = PACK
    version = VERSION

    def __init__(self) -> None:
        super().__init__()
        self.carriers = EndfieldCarriers()
        self.fields = EndfieldFields()
        self.boundaries = EndfieldBoundaries()
        self.flow = EndfieldFlow()
        self.rules = RULES
        self.objective = EndfieldObjective()

    def fabric(self, params: dict[str, Any]) -> Fabric:
        return fabric(params)

    def library(self) -> dict[str, Footprint]:
        """The pack's own footprints: the units and the pylon; machines come with the netlist."""
        return {**UNITS, PYLON_FOOTPRINT.id: PYLON_FOOTPRINT}

    def unit_footprints(self) -> dict[str, Footprint]:
        return {**UNITS, **super().unit_footprints()}


__all__ = ["NAMESPACE", "PACK", "VERSION", "EndfieldPhysics"]
