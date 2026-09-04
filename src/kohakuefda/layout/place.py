"""Blocks: a cell at an anchor and rotation with a chosen port per pin, and the checkpoint
helpers that turn blocks into a placement and back."""

from kohakuefda.layout.geometry import footprint
from kohakuefda.model.cells import CellInstance, Pin
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import (
    Edge,
    Rotation,
    edge_step,
    rotate_cell,
    rotate_edge,
    rotated_size,
)
from kohakuefda.model.layout import Cell, Entry, Rect
from kohakuefda.model.placement import PlacedBlock, Placement
from kohakuefda.model.plan import Finding

PinKey = tuple[str, str]
UNPOWERED_KINDS = ("core", "pylon", "entry")


class PlacementError(RuntimeError):
    """The blocks cannot be packed into the square."""


class Block:
    """A cell with pins at an anchor and rotation; ``ports`` picks each pin's port."""

    def __init__(
        self, block_id: str, cell: CellInstance, powered: bool = False
    ) -> None:
        self.id = block_id
        self.fragment = cell
        self.kind = cell.kind
        self.constraint = cell.constraint
        self.group = cell.group
        self.env = cell.env
        self.width = cell.width
        self.height = cell.height
        self.pins: dict[PinKey, Pin] = {(cell.id, p.id): p for p in cell.pins}
        self.ports: dict[PinKey, int] = dict.fromkeys(self.pins, 0)
        self.powered = powered
        self.x = 0
        self.y = 0
        self.rotation: Rotation = 0
        self._local_cells: list[Cell] = []
        self._local_rects: list[Rect] = []
        self._turned: dict[Rotation, list[Cell]] = {}
        self._ports: dict[Rotation, list[tuple[PinKey, Cell, Edge]]] = {}

    @classmethod
    def of_cell(cls, cell: CellInstance, dataset: Dataset | None = None) -> "Block":
        powered = cell.kind not in UNPOWERED_KINDS and (
            dataset is None
            or any(dataset.machines[m.machine_id].needs_power for m in cell.machines)
        )
        block = cls(cell.id, cell, powered)
        if dataset is not None and cell.machines:
            for placed in cell.machines:
                machine = dataset.machines[placed.machine_id]
                cells = footprint(
                    placed.x, placed.y, machine.width, machine.depth, placed.rotation
                )
                block._local_cells += cells
                xs = [c[0] for c in cells]
                ys = [c[1] for c in cells]
                block._local_rects.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
        else:
            block._local_cells = [
                (x, y) for y in range(cell.height) for x in range(cell.width)
            ]
            block._local_rects = [(0, 0, cell.width, cell.height)]
        return block

    def size(self) -> tuple[int, int]:
        return rotated_size(self.width, self.height, self.rotation)

    def rect(self, pad: int = 0) -> Rect:
        w, h = self.size()
        return (self.x - pad, self.y - pad, self.x + w + pad, self.y + h + pad)

    def _world(self, cell: Cell) -> Cell:
        lx, ly = rotate_cell(cell[0], cell[1], self.width, self.height, self.rotation)
        return (self.x + lx, self.y + ly)

    def cells(self) -> list[Cell]:
        """World cells of every machine footprint in the block."""
        return [self._world(c) for c in self._local_cells]

    def offsets(self, rotation: Rotation) -> list[Cell]:
        """The footprint turned to ``rotation``, in the block's own frame. Worked out once per
        rotation: placement asks for it tens of thousands of times a run and a block's shape
        never changes."""
        turned = self._turned.get(rotation)
        if turned is None:
            turned = [
                rotate_cell(x, y, self.width, self.height, rotation)
                for x, y in self._local_cells
            ]
            self._turned[rotation] = turned
        return turned

    def cells_at(self, x: int, y: int, rotation: Rotation) -> list[Cell]:
        """World cells the block would occupy at an anchor and rotation."""
        return [(x + lx, y + ly) for lx, ly in self.offsets(rotation)]

    def ports_at(self, rotation: Rotation) -> list[tuple[PinKey, Cell, Edge]]:
        """Every port of every pin at a rotation, in the block's own frame."""
        ports = self._ports.get(rotation)
        if ports is None:
            ports = []
            for key, pin in self.pins.items():
                options = [(p.cell, p.edge) for p in pin.alternatives] or [
                    (pin.cell, pin.edge)
                ]
                for cell, edge in options:
                    turned = rotate_cell(
                        cell[0], cell[1], self.width, self.height, rotation
                    )
                    ports.append((key, turned, rotate_edge(edge, rotation)))
            self._ports[rotation] = ports
        return ports

    def machine_rects(self) -> list[Rect]:
        """World rectangles of every machine footprint in the block."""
        out: list[Rect] = []
        for x0, y0, x1, y1 in self._local_rects:
            a = self._world((x0, y0))
            b = self._world((x1 - 1, y1 - 1))
            out.append(
                (
                    min(a[0], b[0]),
                    min(a[1], b[1]),
                    max(a[0], b[0]) + 1,
                    max(a[1], b[1]) + 1,
                )
            )
        return out

    def port_of(self, key: PinKey) -> tuple[Cell, Edge]:
        """The chosen port of a pin in the block's local frame."""
        pin = self.pins[key]
        index = self.ports.get(key, 0)
        if index and index < len(pin.alternatives):
            alternative = pin.alternatives[index]
            return alternative.cell, alternative.edge
        return pin.cell, pin.edge

    def pin_world(self, key: PinKey) -> tuple[Cell, Edge]:
        """World cell and edge of a pin's chosen port under the block's rotation and anchor."""
        cell, edge = self.port_of(key)
        return self._world(cell), rotate_edge(edge, self.rotation)

    def pin_outside(self, key: PinKey) -> Cell:
        cell, edge = self.pin_world(key)
        dx, dy = edge_step(edge)
        return (cell[0] + dx, cell[1] + dy)

    def port_taken(self, key: PinKey, index: int) -> bool:
        """Whether another pin of the block already uses the port alternative ``index`` names."""
        pin = self.pins[key]
        wanted = pin.alternatives[index].index
        for other_key, other in self.pins.items():
            if other_key == key or other.direction != pin.direction:
                continue
            other_index = self.ports.get(other_key, 0)
            chosen = (
                other.alternatives[other_index].index
                if other.alternatives and other_index < len(other.alternatives)
                else None
            )
            if chosen == wanted:
                return True
        return False

    def state(self) -> tuple[int, int, Rotation, dict[PinKey, int]]:
        return self.x, self.y, self.rotation, dict(self.ports)

    def restore(self, state: tuple[int, int, Rotation, dict[PinKey, int]]) -> None:
        self.x, self.y, self.rotation, ports = state
        self.ports = dict(ports)


def overlaps(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def touching(a: Rect, b: Rect) -> bool:
    """Whether two rectangles share at least one cell of edge (corners do not count)."""
    horizontal = (a[2] == b[0] or b[2] == a[0]) and min(a[3], b[3]) > max(a[1], b[1])
    vertical = (a[3] == b[1] or b[3] == a[1]) and min(a[2], b[2]) > max(a[0], b[0])
    return horizontal or vertical


def apply_positions(blocks: list[Block], placement: Placement) -> None:
    """Move every block to its anchor, rotation and ports in ``placement`` (matched by id)."""
    for block in blocks:
        placed = placement.block(block.id)
        block.x, block.y, block.rotation = placed.x, placed.y, placed.rotation
        block.ports = {key: placed.ports.get(key[1], 0) for key in block.pins}


def placed_blocks(blocks: list[Block]) -> list[PlacedBlock]:
    return [
        PlacedBlock(
            id=b.id,
            x=b.x,
            y=b.y,
            rotation=b.rotation,
            width=b.width,
            height=b.height,
            ports={key[1]: index for key, index in b.ports.items() if index},
        )
        for b in blocks
    ]


def placement_of(
    blocks: list[Block],
    pylons: list[Cell],
    entries: list[Entry],
    dataset_version: str,
    square: tuple[int, int],
    grid: tuple[int, int],
    area: Rect,
    gap: int,
    cost: float,
    terms: dict[str, float],
    findings: list[Finding],
) -> Placement:
    """The blocks' current positions as a checkpoint."""
    return Placement(
        dataset_version=dataset_version,
        square=square,
        grid=grid,
        area=area,
        gap=gap,
        cost=cost,
        terms=terms,
        blocks=placed_blocks(blocks),
        pylons=list(pylons),
        entries=list(entries),
        findings=findings,
    )


def catalogue_of(blocks: list[Block]) -> list[dict]:
    """Sizes, kinds, groups, machines and local pins of every block, for drawing frames."""
    return [
        {
            "id": b.id,
            "kind": b.kind,
            "constraint": b.constraint,
            "group": b.group,
            "env": b.env,
            "powered": b.powered,
            "width": b.width,
            "height": b.height,
            "machines": [
                {
                    "id": m.id,
                    "machine_id": m.machine_id,
                    "x": m.x,
                    "y": m.y,
                    "rotation": m.rotation,
                    "recipe_id": m.recipe_id,
                }
                for m in b.fragment.machines
            ],
            "pins": [
                {
                    "id": p.id,
                    "x": p.cell[0],
                    "y": p.cell[1],
                    "edge": p.edge.value,
                    "kind": p.kind,
                    "direction": p.direction,
                    "item_id": p.item_id,
                    "alternatives": [
                        {"x": a.cell[0], "y": a.cell[1], "edge": a.edge.value}
                        for a in p.alternatives
                    ],
                }
                for p in b.pins.values()
            ],
        }
        for b in blocks
    ]
