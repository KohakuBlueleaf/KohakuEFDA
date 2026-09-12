"""Stage 2 defaults: no emitters, the greedy cover planner that ships as the slot's occupant, and a per-kind dispatch."""

from functools import lru_cache
from typing import Any

import numpy as np

from kohakulayout.ir import Cell, Footprint
from kohakulayout.ir.geometry import XY, footprint_cells
from kohakulayout.physics.protocol import Emitter, Reach, UnitPlacement


def reach_cells(emitter: Emitter, x: int, y: int) -> frozenset[XY]:
    """The cells an emitter placed at ``(x, y)`` covers."""
    shape = _shape_of(emitter)
    if len(shape) == 1:
        return _shifted(shape[0], x, y)
    ox, oy, r = shape
    return _square(x + ox, y + oy, r)


Shape = tuple[int, int, int] | tuple[tuple[XY, ...]]
_SHAPES: dict[int, tuple[Emitter, Shape]] = {}


def _shape_of(emitter: Emitter) -> Shape:
    """A reach read once per emitter: a square's centre offset and radius, or a mask's offsets alone."""
    key = id(emitter)
    hit = _SHAPES.get(key)
    if hit is None or hit[0] is not emitter:
        reach = emitter.reach
        shape: Shape = (
            (tuple((dx, dy) for dx, dy in reach.cells),)
            if reach.shape == "mask"
            else (
                emitter.footprint.width // 2,
                emitter.footprint.height // 2,
                reach.radius,
            )
        )
        _SHAPES[key] = (emitter, shape)
        return shape
    return hit[1]


@lru_cache(maxsize=8192)
def _shifted(offsets: tuple[XY, ...], x: int, y: int) -> frozenset[XY]:
    return frozenset((x + dx, y + dy) for dx, dy in offsets)


@lru_cache(maxsize=8192)
def _square(cx: int, cy: int, r: int) -> frozenset[XY]:
    return frozenset(
        (cx + dx, cy + dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
    )


def reach_extent(emitter: Emitter) -> int:
    """How far the reach stretches from the anchor at most, for a square or a mask."""
    reach = emitter.reach
    if reach.shape == "mask":
        return max((max(abs(dx), abs(dy)) for dx, dy in reach.cells), default=0)
    return reach.radius + max(emitter.footprint.width, emitter.footprint.height) // 2


def satisfied(
    need_cells: tuple[XY, ...], covered: frozenset[XY], partial: bool
) -> bool:
    if partial:
        return any(c in covered for c in need_cells)
    return all(c in covered for c in need_cells)


class DefaultFields:
    """No fields: every need is unsatisfiable and ``cover`` places nothing."""

    def needs(self, cell: Cell) -> tuple[str, ...]:
        return cell.needs

    def emitters(self) -> tuple[Emitter, ...]:
        return ()

    def cover(
        self, world: Any, needs: dict[str, tuple[XY, ...]]
    ) -> tuple[UnitPlacement, ...]:
        return ()

    def sweep(self, kind: str) -> bool:
        return False


class GreedyCover:
    """The cover planner slot's default occupant: for each need, the first free anchor whose reach covers it, off every open attach cell while one exists.

    A pack composes it with its emitters; the world calls it inside the placement's
    transaction and treats an uncovered need as a ``field`` refusal. It sweeps no kind.
    """

    def __init__(self, emitters: tuple[Emitter, ...]) -> None:
        self._emitters = {e.kind: e for e in emitters}

    def sweep(self, kind: str) -> bool:
        return False

    def emitters(self) -> tuple[Emitter, ...]:
        return tuple(self._emitters.values())

    def cover(
        self, world: Any, needs: dict[str, tuple[XY, ...]]
    ) -> tuple[UnitPlacement, ...]:
        out: list[UnitPlacement] = []
        for kind, cells in needs.items():
            emitter = self._emitters.get(kind)
            if emitter is None or not cells:
                continue
            covered = world.field_coverage(kind)
            if satisfied(cells, covered, emitter.reach.partial):
                continue
            spot = self._spot(world, emitter, cells)
            if spot is None:
                return ()
            out.append(
                UnitPlacement(
                    kind=kind,
                    footprint=emitter.footprint,
                    x=spot[0],
                    y=spot[1],
                    owner=f"field:{kind}",
                )
            )
        return tuple(out)

    def _spot(self, world: Any, emitter: Emitter, cells: tuple[XY, ...]) -> XY | None:
        fp = emitter.footprint
        target_x = sum(c[0] for c in cells) // len(cells)
        target_y = sum(c[1] for c in cells) // len(cells)
        r = reach_extent(emitter) + max(fp.width, fp.height)
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        candidates = sorted(
            (
                (x, y)
                for y in range(min(ys) - r, max(ys) + r + 1)
                for x in range(min(xs) - r, max(xs) + r + 1)
            ),
            key=lambda xy: abs(xy[0] - target_x) + abs(xy[1] - target_y),
        )
        open_cells = {
            layer: frozenset(owners)
            for layer, owners in world.open_attach_owners().items()
        }
        shut = frozenset().union(
            *(open_cells.get(layer, frozenset()) for layer in world.layers_for(fp))
        )
        partial = emitter.reach.partial
        forbidden = emitter.overlap == "forbidden"
        fallback: XY | None = None
        for x, y in candidates:
            reached = reach_cells(emitter, x, y)
            if not satisfied(cells, reached, partial):
                continue
            if not world.free_footprint(fp, x, y, 0):
                continue
            own = footprint_cells(x, y, fp.width, fp.height, 0)
            if forbidden and world.field_coverage(emitter.kind) & reached:
                continue
            if not all(world.in_build(c) for c in own):
                continue
            if any(c in shut for c in own):
                fallback = fallback or (x, y)
                continue
            return (x, y)
        return fallback


Rect = tuple[int, int, int, int]


def region_rect(world: Any, region: str) -> Rect:
    """The bounding rectangle of a fabric region, exclusive at its far sides."""
    rects = world.fabric.regions[region].rects
    return (
        min(r.x for r in rects),
        min(r.y for r in rects),
        max(r.x + r.w for r in rects),
        max(r.y + r.h for r in rects),
    )


def placed_rect(world: Any, cell_id: str, placement: Any) -> Rect:
    """A placed cell's footprint rectangle, exclusive at its far sides."""
    fp = world.footprint_of(cell_id)
    cells = footprint_cells(
        placement.x, placement.y, fp.width, fp.height, placement.rot
    )
    return (
        placement.x,
        placement.y,
        max(c[0] for c in cells) + 1,
        max(c[1] for c in cells) + 1,
    )


def held_cells(world: Any) -> np.ndarray:
    """Every held cell on any layer as a boolean grid, rows by columns."""
    layers = world.fabric.layers
    used = world.kernel.occupancy(layers[0]) > 0
    for layer in layers[1:]:
        used |= world.kernel.occupancy(layer) > 0
    return used


def free_anchor(window: Rect, used: np.ndarray, size: int) -> XY | None:
    """The first anchor in the window, row by row, whose ``size`` square holds no used cell."""
    x0, y0, x1, y1 = window
    x1, y1 = min(x1, used.shape[1] - size + 1), min(y1, used.shape[0] - size + 1)
    x0, y0 = max(x0, 0), max(y0, 0)
    if x0 >= x1 or y0 >= y1:
        return None
    band = used[y0 : y1 + size - 1, x0 : x1 + size - 1]
    hit = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    for dy in range(size):
        for dx in range(size):
            hit |= band[dy : dy + y1 - y0, dx : dx + x1 - x0]
    free = np.flatnonzero(~hit)
    if not len(free):
        return None
    row, col = divmod(int(free[0]), x1 - x0)
    return (x0 + col, y0 + row)


class SquareSweep:
    """A swept planner for one kind whose emitter is a ``size`` square reaching ``reach`` past it.

    The cells needing the kind, in row order, join the first group whose windows still share
    a free square, else open one; each group gets one emitter on its window's first free
    square inside ``region``.
    """

    def __init__(
        self, kind: str, footprint: Footprint, size: int, reach: int, region: str
    ) -> None:
        self.kind = kind
        self.footprint = footprint
        self.size = size
        self.reach = reach
        self.region = region

    def sweep(self, kind: str) -> bool:
        return kind == self.kind

    def window(self, rect: Rect, area: Rect) -> Rect:
        """The anchors whose square reaches the rectangle, clipped to where an emitter may stand."""
        x0, y0, x1, y1 = rect
        size, reach = self.size, self.reach
        return (
            max(area[0], x0 - size - reach + 1),
            max(area[1], y0 - size - reach + 1),
            min(area[2] - size + 1, x1 + reach),
            min(area[3] - size + 1, y1 + reach),
        )

    def cover(
        self, world: Any, needs: dict[str, tuple[XY, ...]]
    ) -> tuple[UnitPlacement, ...]:
        if self.kind not in needs:
            return ()
        area = region_rect(world, self.region)
        used = held_cells(world)
        fields = world.physics.fields
        rects = sorted(
            (
                placed_rect(world, cell_id, placement)
                for cell_id, placement in world.placements.items()
                if self.kind in fields.needs(world.netlist.cells[cell_id])
            ),
            key=lambda r: (r[1], r[0]),
        )
        groups: list[Rect] = []
        for rect in rects:
            window = self.window(rect, area)
            for index, shared in enumerate(groups):
                merged = (
                    max(shared[0], window[0]),
                    max(shared[1], window[1]),
                    min(shared[2], window[2]),
                    min(shared[3], window[3]),
                )
                if (
                    merged[0] < merged[2]
                    and merged[1] < merged[3]
                    and free_anchor(merged, used, self.size) is not None
                ):
                    groups[index] = merged
                    break
            else:
                if free_anchor(window, used, self.size) is not None:
                    groups.append(window)
        out: list[UnitPlacement] = []
        for window in groups:
            spot = free_anchor(window, used, self.size)
            if spot is None:
                continue
            used[spot[1] : spot[1] + self.size, spot[0] : spot[0] + self.size] = True
            out.append(
                UnitPlacement(
                    kind=self.kind,
                    footprint=self.footprint,
                    x=spot[0],
                    y=spot[1],
                    owner=f"field:{self.kind}",
                )
            )
        return tuple(out)

    def native(self, world: Any) -> dict[str, Any]:
        """The sweep as data for the native twin."""
        return {
            "kind": self.kind,
            "footprint": self.footprint.id,
            "size": self.size,
            "reach": self.reach,
            "area": list(region_rect(world, self.region)),
        }


class KindCover:
    """One planner per field kind, the greedy one for any kind not named; the answer to "one planner or one per kind"."""

    def __init__(
        self, emitters: tuple[Emitter, ...], planners: dict[str, Any] | None = None
    ) -> None:
        self._emitters = tuple(emitters)
        self._greedy = GreedyCover(self._emitters)
        self._planners = dict(planners or {})

    def emitters(self) -> tuple[Emitter, ...]:
        return self._emitters

    def planner(self, kind: str) -> Any:
        return self._planners.get(kind, self._greedy)

    def cover(
        self, world: Any, needs: dict[str, tuple[XY, ...]]
    ) -> tuple[UnitPlacement, ...]:
        out: list[UnitPlacement] = []
        for kind, cells in needs.items():
            spots = self.planner(kind).cover(world, {kind: cells})
            if not spots and not satisfied(
                cells, world.field_coverage(kind), self.reach_partial(kind)
            ):
                return ()
            out.extend(spots)
        return tuple(out)

    def sweep(self, kind: str) -> bool:
        return bool(self.planner(kind).sweep(kind))

    def reach_partial(self, kind: str) -> bool:
        for emitter in self._emitters:
            if emitter.kind == kind:
                return emitter.reach.partial
        return True

    def native(self, world: Any) -> dict[str, Any] | None:
        """The fields as data for the native twin; None when a kind is unswept or has no data form."""
        sweeps = []
        emitters = []
        for emitter in self._emitters:
            planner = self.planner(emitter.kind)
            if not planner.sweep(emitter.kind) or not hasattr(planner, "native"):
                return None
            sweeps.append(planner.native(world))
            ox, oy = 0, 0
            if emitter.reach.shape == "mask":
                offsets = [list(c) for c in emitter.reach.cells]
            else:
                ox, oy = emitter.footprint.width // 2, emitter.footprint.height // 2
                r = emitter.reach.radius
                offsets = [
                    [ox + dx, oy + dy]
                    for dy in range(-r, r + 1)
                    for dx in range(-r, r + 1)
                ]
            emitters.append(
                {
                    "kind": emitter.kind,
                    "footprint": emitter.footprint.id,
                    "offsets": offsets,
                    "partial": emitter.reach.partial,
                }
            )
        return {"sweeps": sweeps, "emitters": emitters}


__all__ = [
    "DefaultFields",
    "GreedyCover",
    "KindCover",
    "Reach",
    "SquareSweep",
    "free_anchor",
    "held_cells",
    "placed_rect",
    "reach_cells",
    "region_rect",
    "satisfied",
]
