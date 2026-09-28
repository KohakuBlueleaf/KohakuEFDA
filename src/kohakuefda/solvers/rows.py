"""Rows on the bus: the framework's floorplan with the project's rows.

The reference layout (game-knowledge PLC-08) is rows of machines parallel to the Depot Bus,
each stage of a chain one row further from it, a Protocol Stash at the end of the row that
makes an output and a Conduit Outlet beside every machine that drinks a liquid, belts along
the rows. ``EndfieldRows`` builds that structure: the free cells ranked by their stage (the
longest chain of nets from a source), one row per stage wrapped to the area's width, the
tallest first, every outlet just before its consumer, every stash and inlet just after its
maker; the rows start inside the Core AIC Area below the band the bus and its bricks take,
and the pack pins the bus itself. Between rows lie the channels, one band per carrier,
against the machines' faces: the framework keeps every attach cell of an unreached pin
for that pin's net, so a trunk in the channel weaves past the ports and the drops land on
them. Legalisation, the surrogate and the mutations are the framework's.
"""

import random
from typing import Any

from kohakuefda.physics.boundaries import area_rect
from kohakuefda.solvers.rows_geometry import (
    AFTER_KINDS,
    BEFORE_KINDS,
    MARGIN,
    MAX_COLUMNS,
    RowsGeometry,
    item_of,
    partners,
    stages,
)
from kohakulayout.solvers import register
from kohakulayout.solvers.structural import Floorplan, Rows
from kohakulayout.solvers.structural.floorplan import Structure, item_size, items_of


@register
class EndfieldRows(RowsGeometry, Rows):
    """Rows by stage inside the area, side cells beside their partners, below the bus band."""

    id = "endfield.rows"

    def initial(self, ctx: Any, rng: random.Random) -> Structure:
        """The stack wrapped to the whole area's width, or to a half, a third, ... of it, the
        first that folds into that many columns (``fold``)."""
        world = ctx.world
        x0, _, x1, _ = area_rect(world.fabric)
        width = x1 - x0 - 2 * MARGIN
        best: tuple[int, Structure] | None = None
        for count in range(1, MAX_COLUMNS + 1):
            limit = (width - (count - 1) * self.channel) // count
            structure = self.stacked(ctx, limit)
            structure["columns"] = count
            over = self.overflow(structure, ctx)
            if best is None or over < best[0]:
                best = (over, structure)
            if over <= 0:
                break
        return best[1]

    def stacked(self, ctx: Any, limit: int) -> Structure:
        """Blocks on shelves: one block per root unit (the blocks of the feeders only it uses
        on shelves above it, recursively, its own group last), one per group of units that
        feed several blocks (their rows by stage), one per loose side cell; the shared
        blocks in flow order: the ones the bus feeds first (they land under the bus), then
        by the earliest stage among their units, the taller first among equals; blocks side
        by side while they fit ``limit``."""
        world = ctx.world
        netlist = world.problem.netlist
        items = items_of(world)
        kinds = {c: netlist.cells[c].kind for c in items}
        stage = stages(netlist)
        rot: dict[str, int] = {}
        sinks_of = {
            c: [s for s in partners(netlist, c, "out") if s in kinds] for c in items
        }
        sources_of = {
            c: [s for s in partners(netlist, c, "in") if s in kinds] for c in items
        }
        side = {c for c in items if kinds[c] in BEFORE_KINDS | AFTER_KINDS}
        main = [c for c in items if c not in side]
        feeds = {c: [s for s in sinks_of[c] if s not in side] for c in main}
        fed = {c: [s for s in sources_of[c] if s not in side] for c in main}
        roots = [c for c in main if not feeds[c] and fed[c]]
        before: dict[str, list[str]] = {}
        after: dict[str, list[str]] = {}
        loose: list[str] = []
        for cell_id in sorted(side):
            if kinds[cell_id] in BEFORE_KINDS:
                mates = sinks_of[cell_id]
                (before.setdefault(mates[0], []) if mates else loose).append(cell_id)
            else:
                mates = sources_of[cell_id]
                (after.setdefault(mates[0], []) if mates else loose).append(cell_id)

        def group(cell_id: str) -> list[str]:
            return [*before.get(cell_id, []), cell_id, *after.get(cell_id, [])]

        taken: set[str] = set()

        def block(cell_id: str) -> list[list[str]]:
            """The unit's rows: the blocks of the feeders only it uses on shelves above it, then its own group."""
            taken.add(cell_id)
            children = sorted(
                f for f in fed[cell_id] if f not in taken and feeds[f] == [cell_id]
            )
            rows = self.block_rows(world, [block(c) for c in children], limit, rot)
            return [*rows, group(cell_id)]

        blocks = [block(r) for r in sorted(roots, key=lambda c: (stage.get(c, 0), c))]
        rest = [c for c in main if c not in taken]
        shared: list[list[list[str]]] = []
        for component in self.components(rest, feeds, fed):
            levels: dict[int, list[str]] = {}
            for c in sorted(component):
                levels.setdefault(stage.get(c, 0), []).append(c)
            shared.append(
                self.wrapped(
                    world,
                    [((k, 0), group(c)) for k in sorted(levels) for c in levels[k]],
                    limit,
                    rot,
                )
            )

        def tall(rows_: list[list[str]]) -> int:
            return sum(max(item_size(world, c, 0)[1] for c in row) for row in rows_)

        from_bus = {
            c for c in main if any(s not in kinds for s in partners(netlist, c, "in"))
        }

        def bus_first(rows_: list[list[str]]) -> int:
            return 0 if any(c in from_bus for row in rows_ for c in row) else 1

        def flow(rows_: list[list[str]]) -> tuple[int, int, int]:
            return (
                bus_first(rows_),
                min(stage.get(c, 0) for row in rows_ for c in row),
                -tall(rows_),
            )

        ordered = sorted([*shared, *blocks], key=flow)
        rows = self.block_rows(world, [*ordered, *([[c]] for c in loose)], limit, rot)
        return {
            "rows": rows,
            "rot": rot,
            "bands": self.bands_of(world, rows),
            "blocks": blocks,
        }

    def components(
        self, cells: list[str], feeds: dict[str, list[str]], fed: dict[str, list[str]]
    ) -> list[list[str]]:
        """The cells grouped by the flows among them, in first-seen order."""
        parent = {c: c for c in cells}

        def find(c: str) -> str:
            while parent[c] != c:
                c = parent[c]
            return c

        for c in cells:
            for other in [*feeds[c], *fed[c]]:
                if other in parent:
                    parent[find(other)] = find(c)
        groups: dict[str, list[str]] = {}
        for c in cells:
            groups.setdefault(find(c), []).append(c)
        return list(groups.values())

    def bands_of(self, world: Any, rows: list[list[str]]) -> list[int]:
        """The channel rows above each row: one where every net across the boundary is a lane
        from one item in the row above to one item in this row (an aligned drop of one cell);
        elsewhere two attach rows and one per net that runs along the band on its layer (a
        pin in the row below fed from elsewhere, a pin in the row above feeding elsewhere),
        at least the channel; the bus channel above the first row sized the same way."""
        row_of = {c: k for k, row in enumerate(rows) for c in row}
        out: list[int] = []
        for k in range(len(rows)):
            along: dict[str, int] = {}
            drops_only = k > 0
            for net in world.netlist.nets.values():
                if "/" in net.id:
                    continue
                sources = [row_of.get(item_of(r.cell)) for r in net.sources]
                sinks = [row_of.get(item_of(r.cell)) for r in net.sinks]
                known = [r for r in [*sources, *sinks] if r is not None]
                if k > 0 and sources == [k - 1] and sinks == [k]:
                    continue
                if k not in sinks and (k - 1) not in sources:
                    if k == 0 and None in sources and known:
                        along[net.carrier] = along.get(net.carrier, 0) + 1
                    continue
                drops_only = False
                along[net.carrier] = along.get(net.carrier, 0) + 1
            if drops_only:
                out.append(1)
            else:
                out.append(max(self.channel, 2 + max(along.values(), default=0)))
        return out

    def wrapped(
        self,
        world: Any,
        groups: list[tuple[tuple[int, int], list[str]]],
        limit: int,
        rot: dict[str, int] | None = None,
    ) -> list[list[str]]:
        """One row per stage, broken into more when a group of a machine and its side cells
        would outgrow ``limit``; a group never splits."""
        rows: list[list[str]] = []
        level = None
        used = 0
        turned = rot or {}
        for key, group in groups:
            width = sum(
                item_size(world, c, turned.get(c, 0))[0] + self.gap for c in group
            )
            if level != key or used + width > limit:
                rows.append([])
                used = 0
                level = key
            rows[-1] += group
            used += width
        return [r for r in rows if r]

    def block_rows(
        self,
        world: Any,
        blocks: list[list[list[str]]],
        limit: int,
        rot: dict[str, int] | None = None,
    ) -> list[list[str]]:
        """Blocks side by side on a shelf while they fit ``limit``, their last rows on the
        shelf's last row and their rows above aligned to it, deeper blocks reaching higher;
        the blocks that do not fit on shelves above."""
        turned = rot or {}

        def width(cells: list[str]) -> int:
            return sum(
                item_size(world, c, turned.get(c, 0))[0] + self.gap for c in cells
            )

        rows: list[list[str]] = []
        pending: list[list[list[str]]] = []
        used = 0
        for levels in [*blocks, None]:
            span = max((width(level) for level in levels), default=0) if levels else 0
            if pending and (levels is None or used + span > limit):
                depth = max(len(b) for b in pending)
                for offset in range(depth):
                    row: list[str] = []
                    for block in pending:
                        level = offset - (depth - len(block))
                        if level >= 0:
                            row += block[level]
                    rows.append(row)
                pending, used = [], 0
            if levels is not None:
                pending.append(levels)
                used += span
        return [r for r in rows if r]

    def mutate(self, structure: Structure, rng: random.Random) -> Structure:
        """The framework's moves between and along rows; nothing turns."""
        out = super().mutate(structure, rng)
        out["rot"] = {}
        return out


@register
class EndfieldFloorplan(Floorplan):
    id = "endfield.floorplan"

    def representation(self) -> Any:
        if self.opts["representation"] == "rows":
            return EndfieldRows(
                channel=self.opts["channel"],
                gap=self.opts["gap"],
                rows=self.opts["rows"],
            )
        return super().representation()


__all__ = ["EndfieldFloorplan", "EndfieldRows", "partners", "stages"]
