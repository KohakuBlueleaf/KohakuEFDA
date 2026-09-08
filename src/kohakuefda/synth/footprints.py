"""Machines as framework footprints: size from the dataset, every port as a side and an offset.

A machine occupies the ground and shades the sky above it, so no pipe runs over it; its
belt ports lie on the ground and its pipe ports overhead. An outside input is a 1×1 border
cell whose pipe leaves eastward at rotation zero (RES-09).
"""

from kohakuefda.model.cells import CellInstance, Pin
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.machines import Machine
from kohakuefda.model.machines import Port as MachinePort
from kohakuefda.physics.fabric import NAMESPACE
from kohakuefda.physics.library import GROUND, SKY
from kohakulayout.ir import Footprint, Port
from kohakulayout.ir.geometry import ROTATIONS

ENTRY = "entry"
ENTRY_PORT = "out0"


def port_id(direction: str, index: int) -> str:
    return f"{direction}{index}"


def port_of(port: MachinePort) -> Port:
    side = port.edge.value
    offset = port.x if side in ("N", "S") else port.y
    return Port(
        id=port_id(port.direction.value, port.index),
        side=side,
        offset=offset,
        direction=port.direction.value,
        carrier=port.type.value,
        attrs={NAMESPACE: {"index": port.index, "layer": port.layer}},
    )


def footprint_of(machine: Machine) -> Footprint:
    return Footprint(
        id=machine.id,
        width=machine.width,
        height=machine.depth,
        layer=GROUND,
        occludes=(SKY,),
        rotations=ROTATIONS,
        ports=tuple(port_of(p) for p in machine.ports),
        attrs={
            NAMESPACE: {
                "machine": machine.id,
                "power": machine.power,
                "needs_power": machine.needs_power,
            }
        },
    )


ENTRY_FOOTPRINT = Footprint(
    id=ENTRY,
    width=1,
    height=1,
    layer=GROUND,
    occludes=(SKY,),
    rotations=ROTATIONS,
    ports=(Port(id=ENTRY_PORT, side="E", offset=0, direction="out", carrier="pipe"),),
    attrs={
        NAMESPACE: {
            "machine": ENTRY,
            "power": 0,
            "needs_power": False,
            "facts": ["RES-09"],
        }
    },
)


def library_of(dataset: Dataset, cells: list[CellInstance]) -> dict[str, Footprint]:
    """One footprint per machine the cells use, plus the outside input."""
    out: dict[str, Footprint] = {}
    for cell in cells:
        if cell.machine_id == ENTRY:
            out[ENTRY] = ENTRY_FOOTPRINT
        elif cell.machine_id not in out:
            out[cell.machine_id] = footprint_of(dataset.machines[cell.machine_id])
    return out


def ports_for(fp: Footprint, pin: Pin) -> tuple[str, ...]:
    """The pin's port ids: its default first, then every alternative it may use instead."""
    if fp.id == ENTRY:
        return (ENTRY_PORT,)
    default = next(
        (
            p.id
            for p in fp.ports
            if p.direction == pin.direction
            and p.side == pin.edge.value
            and (p.offset == (pin.cell[0] if p.side in ("N", "S") else pin.cell[1]))
        ),
        None,
    )
    others = [
        port_id(pin.direction, ref.index)
        for ref in pin.alternatives
        if fp.port(port_id(pin.direction, ref.index)) is not None
    ]
    ordered = [default] if default is not None else []
    ordered += [o for o in others if o not in ordered]
    return tuple(ordered)


__all__ = [
    "ENTRY",
    "ENTRY_FOOTPRINT",
    "ENTRY_PORT",
    "footprint_of",
    "library_of",
    "port_id",
    "port_of",
    "ports_for",
]
