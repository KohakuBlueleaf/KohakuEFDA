"""L3 shapes: ports, footprints, pins, constraints, cells, pin references, nets, groups."""

from fractions import Fraction
from typing import Literal

from kohakulayout.ir.base import Attrs, Model, Node, Rate, check_attrs, check_id
from kohakulayout.ir.geometry import ROTATIONS, SIDES, Rotation, Side, side_length

Direction = Literal["in", "out", "inout"]
DIRECTIONS: tuple[str, ...] = ("in", "out", "inout")


class Port(Model):
    id: str
    side: Side
    offset: int
    direction: Direction
    carrier: str
    attrs: Attrs = {}


class Footprint(Model):
    id: str
    width: int
    height: int
    layer: str = "ground"
    occludes: tuple[str, ...] = ()
    rotations: tuple[Rotation, ...] = ROTATIONS
    ports: tuple[Port, ...] = ()
    attrs: Attrs = {}

    def port(self, port_id: str) -> Port | None:
        for port in self.ports:
            if port.id == port_id:
                return port
        return None

    def check(self, where: str = "") -> list[str]:
        where = where or f"footprint {self.id}"
        problems = check_id(self.id, where)
        if self.width < 1 or self.height < 1:
            problems.append(f"{where}: width and height must be positive")
        if not self.rotations:
            problems.append(f"{where}: no rotation is allowed")
        if self.layer in self.occludes:
            problems.append(f"{where}: occludes its own layer")
        seen: set[str] = set()
        for port in self.ports:
            if port.id in seen:
                problems.append(f"{where}: port {port.id!r} appears twice")
            seen.add(port.id)
            if port.side not in SIDES:
                problems.append(
                    f"{where}: port {port.id!r} side {port.side!r} is not N, E, S or W"
                )
            elif not 0 <= port.offset < side_length(self.width, self.height, port.side):
                problems.append(
                    f"{where}: port {port.id!r} offset {port.offset} is off its side"
                )
            problems += check_attrs(port.attrs, f"{where} port {port.id}")
        problems += check_attrs(self.attrs, where)
        return problems


class Pin(Model):
    id: str
    direction: Direction
    carrier: str
    ports: tuple[str, ...] = ()


class Constraint(Model):
    kind: str = "free"
    attrs: Attrs = {}


class Cell(Node):
    footprint: str | None = None
    module: str | None = None
    macro: str | None = None
    pins: tuple[Pin, ...] = ()
    constraint: Constraint = Constraint()
    group: str | None = None
    needs: tuple[str, ...] = ()

    @property
    def is_instance(self) -> bool:
        return self.module is not None or self.macro is not None


class PinRef(Model):
    cell: str
    pin: str

    def __str__(self) -> str:
        return f"{self.cell}.{self.pin}"


class Net(Node):
    carrier: str
    rate: Rate = Fraction(0)
    sources: tuple[PinRef, ...] = ()
    sinks: tuple[PinRef, ...] = ()
    outside: Side | None = None

    def pins(self) -> tuple[PinRef, ...]:
        return self.sources + self.sinks


class Group(Node):
    members: tuple[str, ...] = ()
