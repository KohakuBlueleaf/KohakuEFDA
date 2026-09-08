"""Stage 2 defaults: no emitters, the greedy cover planner that ships as the slot's occupant, and a per-kind dispatch."""

from typing import Any

from kohakulayout.ir import Cell
from kohakulayout.ir.geometry import XY, footprint_cells
from kohakulayout.physics.protocol import Emitter, Reach, UnitPlacement


def reach_cells(emitter: Emitter, x: int, y: int) -> frozenset[XY]:
    """The cells an emitter placed at ``(x, y)`` covers."""
    reach = emitter.reach
    if reach.shape == "mask":
        return frozenset((x + dx, y + dy) for dx, dy in reach.cells)
    r = reach.radius
    cx, cy = x + emitter.footprint.width // 2, y + emitter.footprint.height // 2
    return frozenset(
        (cx + dx, cy + dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
    )


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
    """The cover planner slot's default occupant: for each need, the first free anchor whose reach covers it.

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
        r = emitter.reach.radius + max(fp.width, fp.height)
        candidates = sorted(
            (
                (x, y)
                for y in range(target_y - r, target_y + r + 1)
                for x in range(target_x - r, target_x + r + 1)
            ),
            key=lambda xy: abs(xy[0] - target_x) + abs(xy[1] - target_y),
        )
        shut = world.open_attach_cells().get(fp.layer, frozenset())
        for x, y in candidates:
            if not satisfied(cells, reach_cells(emitter, x, y), emitter.reach.partial):
                continue
            if not world.free_footprint(fp, x, y, 0):
                continue
            if any(c in shut for c in footprint_cells(x, y, fp.width, fp.height, 0)):
                continue
            if emitter.overlap == "forbidden" and world.field_coverage(
                emitter.kind
            ) & reach_cells(emitter, x, y):
                continue
            if all(
                world.in_build(c) for c in footprint_cells(x, y, fp.width, fp.height, 0)
            ):
                return (x, y)
        return None


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
