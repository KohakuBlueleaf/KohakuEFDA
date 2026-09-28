"""The shape of the lines: which bus face each group takes, how wide it may be and
where a row too wide for that folds.

The finished bases (game-knowledge PLC-09) put the groups the depot feeds on the bus
line; a fixed bus has slots on two faces, so a line that finds no room on the north face
takes the west face, turned to read from it. A bus-fed row keeps its width (its bricks
stand edge to edge on the slots) and the deeper rows fold to it.
"""

from typing import Any

from kohakuefda.physics.boundaries import BUS_ROOM, area_rect
from kohakuefda.physics.fabric import slots_of
from kohakuefda.solvers.lines_graph import LineGraph
from kohakuefda.solvers.rows_geometry import MARGIN
from kohakulayout.solvers.structural.floorplan import Structure, item_size


def room_of(world: Any) -> tuple[int, int, int, int]:
    """Where the groups may stand: the whole Core AIC Area on a fixed bus (its slots
    are the area's border), else the area past the bus room and a margin on the bus
    side."""
    x0, y0, x1, y1 = area_rect(world.fabric)
    if slots_of(world.fabric):
        return (x0, y0, x1, y1)
    return (x0 + BUS_ROOM + MARGIN, y0 + BUS_ROOM + MARGIN, x1, y1)


BUDGET_SLACK = 2


class LinesShape:
    """The face, budget and fold half of ``EndfieldLines``; mixed into it."""

    channel: int

    def graph(self, world: Any) -> LineGraph: ...

    def group_layout(self, *args: Any, **kwargs: Any) -> Any: ...

    def pack(self, *args: Any, **kwargs: Any) -> Any: ...

    def line_faces(self, structure: Structure, ctx: Any) -> list[str | None]:
        """The bus face per group: the bus groups take the north face in order while
        its slots hold their bricks (every group on a laid bus) and its length holds
        their widest rows side by side, then the west face on the same terms; a group
        the bus does not feed takes none."""
        world = ctx.world
        graph = self.graph(world)
        slots = slots_of(world.fabric)
        room = {
            "N": sum(1 for s in slots if s[2] == "N"),
            "W": sum(1 for s in slots if s[2] == "W"),
        }
        if not slots:
            room["N"] = 10**6
        used = {"N": 0, "W": 0}
        left, top, right, bottom = room_of(world)
        length = {"N": right - left, "W": bottom - top}
        taken = {"N": 0, "W": 0}
        rot = structure["rot"]
        out: list[str | None] = []
        for rows in structure["groups"]:
            bricks = sum(1 for i in rows[0] if i in graph.bricks) if rows else 0
            if not bricks:
                out.append(None)
                continue
            width = max(
                (self.row_width(graph, row, rot) for row in rows if row), default=0
            )
            face = "N"
            for candidate in ("N", "W"):
                fits = used[candidate] + bricks <= room[candidate]
                along = (
                    taken[candidate] + width + (self.channel if taken[candidate] else 0)
                )
                if fits and (along <= length[candidate] or not taken[candidate]):
                    face = candidate
                    break
            used[face] += bricks
            taken[face] += width + (self.channel if taken[face] else 0)
            out.append(face)
        return out

    def row_width(self, graph: LineGraph, row: list[str], rot: dict[str, int]) -> int:
        """The width of a row packed on its own, edge to edge when the bus feeds it or a loop is all of it."""
        xs: dict[str, int] = {}
        self.pack(graph, row, xs, {}, rot)
        return max(
            (xs[i] + sum(graph.span(i, rot.get(i, 0))[1:3]) for i in row), default=0
        ) - min((xs[i] - graph.span(i, rot.get(i, 0))[0] for i in row), default=0)

    def budgets(self, structure: Structure, ctx: Any) -> list[int]:
        """The width each group may take. A north group takes the share of the room's
        width its machines' cells are of every group's, so the groups off the bus
        find room beside it, no more than the room the other north groups' least
        widths leave nor its widest row packed alone plus ``BUDGET_SLACK`` (so rows
        aligned to a partner do not drift the group wide), and at least its own least
        width (its bus-fed row and widest loop); a west group takes the west face's
        length left under the north groups, at least its least width; every other
        group the widest north group's width, at least its least width."""
        world = ctx.world
        graph = self.graph(world)
        left, top, right, bottom = room_of(world)
        limit = right - left
        length = bottom - top
        groups = structure["groups"]
        faces = structure.get("faces") or [None] * len(groups)
        rot = structure["rot"]
        floors = [
            self.row_width(graph, rows[1], rot) if len(rows) > 1 and faces[g] else 0
            for g, rows in enumerate(groups)
        ]
        for g, rows in enumerate(groups):
            for row in rows:
                for item in row:
                    loop = [i for i in graph.loop_of(item) if i in row]
                    if len(loop) > 1:
                        floors[g] = max(floors[g], self.row_width(graph, loop, rot))
        north = [g for g in range(len(groups)) if faces[g] == "N"]
        room = limit - self.channel * (len(north) - 1)
        areas = [
            sum(
                item_size(world, i, 0)[0] * item_size(world, i, 0)[1]
                for row in rows
                for i in row
            )
            for rows in groups
        ]
        total = sum(areas)
        out = [limit] * len(groups)
        for g in north:
            others = sum(floors[h] for h in north if h != g)
            share = room * areas[g] // total if total else limit
            natural = max(
                (self.row_width(graph, row, rot) for row in groups[g][1:] if row),
                default=0,
            )
            out[g] = max(floors[g], min(room - others, share, natural + BUDGET_SLACK))
        depth = max(
            (self.group_layout(graph, groups[g], rot, out[g])[2] for g in north),
            default=0,
        )
        widest = max((out[g] for g in north), default=limit)
        for g in range(len(groups)):
            if faces[g] == "W":
                out[g] = max(floors[g], length - depth - self.channel)
            elif faces[g] is None:
                out[g] = max(floors[g], widest)
        return out

    def fold(self, structure: Structure, ctx: Any) -> bool:
        """Every group wider than its budget has its widest row past the bus-fed one
        cut when that row alone is wider than the budget: the items past the width
        move to a new row under it, a loop whole, or, when they are the row's guests
        and the row under holds no loop and has the room, into that row; a group
        within its budget moves the outermost guest of its widest row the same way
        when that makes the group's area smaller. Whether any row changed."""
        world = ctx.world
        graph = self.graph(world)
        rot = structure["rot"]
        budgets = self.budgets(structure, ctx)
        cut = False
        for g, rows in enumerate(structure["groups"]):
            budget = budgets[g]
            boxes, width, height, _ = self.group_layout(graph, rows, rot, budget)
            over = width > budget
            edges = {
                i: boxes[i][0] + boxes[i][2] + graph.span(i, rot.get(i, 0))[2]
                for row in rows
                for i in row
            }
            starts = {i: boxes[i][0] - graph.span(i, rot.get(i, 0))[0] for i in edges}
            first = 1 if rows and rows[0] else 0
            spans = {
                k: max(map(edges.get, row), default=0)
                - min(map(starts.get, row), default=0)
                for k, row in enumerate(rows)
                if k > first
            }
            if not spans:
                continue
            k = max(spans, key=spans.get)
            guests = graph.guests(rows[k], rot)
            if over and spans[k] > budget:
                start = min(map(starts.get, rows[k]))
                keep = [i for i in rows[k] if edges[i] - start <= budget]
                rest = [i for i in rows[k] if i not in keep]
            elif guests and spans[k] >= max(spans.values()):
                far = max(
                    guests,
                    key=lambda i: (
                        starts[i] - min(map(starts.get, rows[k]))
                        > edges[i] - max(map(edges.get, rows[k])),
                        edges[i],
                    ),
                )
                keep = [i for i in rows[k] if i != far]
                rest = [far]
            else:
                continue
            for item in list(keep):
                loop = graph.loop_of(item)
                if len(loop) > 1 and any(i in rest for i in loop):
                    keep = [i for i in keep if i not in loop]
                    rest = [i for i in rows[k] if i not in keep]
            if not keep or not rest:
                continue
            below = rows[k + 1] if k + 1 < len(rows) else None
            joins = (
                below is not None
                and set(rest) <= set(guests)
                and all(len(graph.loop_of(i)) == 1 for i in below)
                and self.row_width(graph, below + rest, rot) <= max(budget, width)
            )
            trial = [list(row) for row in rows]
            trial[k] = keep
            if joins:
                trial[k + 1] = below + rest
            else:
                trial.insert(k + 1, rest)
            _, new_width, new_height, _ = self.group_layout(graph, trial, rot, budget)
            if not over and new_width * new_height >= width * height:
                continue
            rows[:] = trial
            cut = True
        return cut


__all__ = ["LinesShape", "room_of"]
