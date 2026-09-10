"""Stage 2 defaults: no emitters, the greedy cover planner that ships as the slot's occupant, and a per-kind dispatch."""

from functools import lru_cache
from typing import Any

from kohakulayout.ir import Cell
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


class GreedyCover:
    """The cover planner slot's default occupant: for each need, the first free anchor whose reach covers it, off every open attach cell while one exists.

    A pack composes it with its emitters; the world calls it inside the placement's
    transaction and treats an uncovered need as a ``field`` refusal.
    """

    def __init__(self, emitters: tuple[Emitter, ...]) -> None:
        self._emitters = {e.kind: e for e in emitters}

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

    def reach_partial(self, kind: str) -> bool:
        for emitter in self._emitters:
            if emitter.kind == kind:
                return emitter.reach.partial
        return True


__all__ = [
    "DefaultFields",
    "GreedyCover",
    "KindCover",
    "Reach",
    "reach_cells",
    "satisfied",
]
