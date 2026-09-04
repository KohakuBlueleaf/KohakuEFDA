"""Logistics units and the game's logistics constants."""

from fractions import Fraction

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.machines import Port
from kohakuefda.model.names import Names
from kohakuefda.model.rates import Rate


class LogisticsUnit(EfdaModel):
    """Belt, pipe, splitter, converger, bridge, control port or conduit end."""

    id: str
    names: Names
    kind: str
    width: int = 1
    depth: int = 1
    height: int = 1
    ms_per_round: int
    volume: int = 1
    ports: list[Port] = []
    capacity: int | None = None

    @property
    def rate_per_min(self) -> Fraction:
        return Fraction(60000 * self.volume, self.ms_per_round)


class LogisticsConstants(EfdaModel):
    """Throughputs, run limits, counts and blueprint limits used by planning and DRC."""

    belt_per_min: Rate
    pipe_per_min: Rate
    belt_run_max: int
    pipe_run_max: int
    conduit_link_max: int
    fluid_router_limit: int
    farmland_limit: int
    blueprint_max_x: int
    blueprint_max_z: int
    blueprint_max_nodes: int
    building_height_diff_max: int
    control_port_limit: dict[str, int] = {}
    core_power: int = 200
    core_power_storage: int = 100000
