"""``BasePhysics``: every hook with its default. A pack subclasses it and overrides what its game has."""

from typing import Any

from kohakulayout.ir import Fabric, Footprint, Refusal
from kohakulayout.ir.refusal import STAGES
from kohakulayout.physics.boundaries import DefaultBoundaries
from kohakulayout.physics.carriers import DefaultCarriers
from kohakulayout.physics.diagnose import diagnose
from kohakulayout.physics.fields import DefaultFields
from kohakulayout.physics.flow import DefaultFlow
from kohakulayout.physics.objective import DefaultObjective


class BasePhysics:
    """The default occupant of every hook. ``fabric`` and ``library`` are what a pack is; the rest is optional."""

    id: str = "null"
    version: str = "0"
    stages: tuple[str, ...] = STAGES

    def __init__(self) -> None:
        self.carriers = DefaultCarriers()
        self.fields = DefaultFields()
        self.boundaries = DefaultBoundaries()
        self.flow = DefaultFlow()
        self.rules: tuple[Any, ...] = ()
        self.objective = DefaultObjective()

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def fabric(self, params: dict[str, Any]) -> Fabric:
        raise NotImplementedError(f"physics {self.id!r} declares no fabric")

    def library(self) -> dict[str, Footprint]:
        raise NotImplementedError(f"physics {self.id!r} declares no library")

    def unit_footprints(self) -> dict[str, Footprint]:
        """Footprints of the units the router and the cover planner may place; emitters by default."""
        return {e.footprint.id: e.footprint for e in self.fields.emitters()}

    def diagnose(self, world: Any, failures: tuple[Refusal, ...]) -> Refusal:
        return diagnose(failures, self.stages)
