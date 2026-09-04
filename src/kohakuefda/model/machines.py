"""Machines and their ports."""

from enum import StrEnum

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.geometry import (
    Edge,
    Rotation,
    rotate_cell,
    rotate_edge,
    rotated_size,
)
from kohakuefda.model.names import Names

GROUND = 0
SKY = 1


class PortType(StrEnum):
    BELT = "belt"
    PIPE = "pipe"


class PortDir(StrEnum):
    IN = "in"
    OUT = "out"


class Port(EfdaModel):
    """One port: cell inside the unrotated footprint, the edge it faces, and its layer."""

    index: int
    direction: PortDir
    type: PortType
    x: int
    y: int
    edge: Edge
    layer: int = GROUND

    def rotated(self, width: int, depth: int, rotation: Rotation) -> "Port":
        """The same port after rotating the footprint clockwise."""
        x, y = rotate_cell(self.x, self.y, width, depth, rotation)
        return self.model_copy(
            update={"x": x, "y": y, "edge": rotate_edge(self.edge, rotation)}
        )


class Mode(EfdaModel):
    """A machine mode: which recipe group it enables and whether it starts unlocked."""

    name: str
    group_id: str | None = None
    unlocked_by_default: bool = True
    env_mode: bool = False


class Machine(EfdaModel):
    """A placeable facility with footprint, ports, power and modes."""

    id: str
    names: Names
    kind: str
    width: int
    depth: int
    height: int
    model_height: float = 0.0
    ports: list[Port] = []
    power: int = 0
    needs_power: bool = False
    capacity_cost: int = 0
    modes: list[Mode] = []
    place_domains: list[str] = []
    recommend_domains: list[str] = []

    def size(self, rotation: Rotation = 0) -> tuple[int, int]:
        return rotated_size(self.width, self.depth, rotation)

    def ports_at(self, rotation: Rotation = 0) -> list[Port]:
        return [p.rotated(self.width, self.depth, rotation) for p in self.ports]

    def ports_of(
        self, direction: PortDir, port_type: PortType | None = None
    ) -> list[Port]:
        return [
            p
            for p in self.ports
            if p.direction is direction and (port_type is None or p.type is port_type)
        ]

    @property
    def is_producer(self) -> bool:
        return any(m.group_id for m in self.modes)
