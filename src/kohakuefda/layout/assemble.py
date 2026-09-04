"""Placed blocks and pylons → one layout, and the ports every pin may use in world cells."""

import logging

from kohakuefda.layout.fragments import place, rotate
from kohakuefda.layout.place import Block, PinKey
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge, edge_step, rotate_cell, rotate_edge
from kohakuefda.model.layout import Cell, Layout, Placed, Rect
from kohakuefda.model.scenario import BasementRef

PYLON = "power_diffuser_1"
log = logging.getLogger(__name__)


class PortOption:
    """One port a lane may use: its index on the machine, its cell, its edge, the cell it faces."""

    def __init__(self, index: int, cell: Cell, edge: Edge) -> None:
        self.index = index
        self.cell = cell
        self.edge = edge
        dx, dy = edge_step(edge)
        self.outside: Cell = (cell[0] + dx, cell[1] + dy)


class WorldPin:
    """A pin in world coordinates: every port its lane may use, in preference order."""

    def __init__(
        self, key: PinKey, options: list[PortOption], kind: str, direction: str
    ) -> None:
        self.key = key
        self.options = options
        self.kind = kind
        self.direction = direction

    @property
    def default(self) -> PortOption:
        return self.options[0]

    @property
    def cell(self) -> Cell:
        return self.options[0].cell

    @property
    def edge(self) -> Edge:
        return self.options[0].edge

    @property
    def outside(self) -> Cell:
        return self.options[0].outside


def assemble(
    dataset: Dataset,
    blocks: list[Block],
    dataset_version: str,
    basement: BasementRef,
    width: int,
    height: int,
    area: Rect | None = None,
    pylons: list[Cell] | None = None,
    pylon_id: str = PYLON,
) -> Layout:
    """A layout holding every block's entities at its anchor plus a pylon per anchor given."""
    layout = Layout(
        dataset_version=dataset_version,
        basement=basement,
        width=width,
        height=height,
        area=area,
    )
    for block in blocks:
        fragment = (
            rotate(dataset, block.fragment, block.rotation)
            if block.rotation
            else block.fragment
        )
        place(layout, fragment, block.x, block.y)
    for index, (x, y) in enumerate(pylons or []):
        layout.machines.append(
            Placed(id=f"pylon{index}", machine_id=pylon_id, x=x, y=y)
        )
    return layout


def world_pins(blocks: list[Block]) -> dict[PinKey, WorldPin]:
    """Every pin of every block with all the ports it may use, the block's chosen one first."""
    out: dict[PinKey, WorldPin] = {}
    for block in blocks:
        for key, pin in block.pins.items():
            chosen, _ = block.port_of(key)
            options: list[PortOption] = []
            for alternative in pin.alternatives or []:
                cell = rotate_cell(
                    alternative.cell[0],
                    alternative.cell[1],
                    block.width,
                    block.height,
                    block.rotation,
                )
                options.append(
                    PortOption(
                        alternative.index,
                        (block.x + cell[0], block.y + cell[1]),
                        rotate_edge(alternative.edge, block.rotation),
                    )
                )
            if not options:
                cell, edge = block.pin_world(key)
                options = [PortOption(0, cell, edge)]
            options.sort(key=lambda o: o.cell != block.pin_world(key)[0])
            out[key] = WorldPin(key, options, pin.kind, pin.direction)
            if chosen is None:
                log.debug("pin %s has %d port option(s)", key, len(options))
    return out
