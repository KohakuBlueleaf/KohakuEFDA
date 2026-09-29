"""The lines seed: the community shape (game-knowledge PLC-09 to PLC-13) laid in one batch.

Rows by depth from the Depot Bus: the unloaders on the bus in front of the machines they
feed, each next stage one lane further, side cells beside their machine, a chain a group
of its own, the groups packed against the bus faces; the lanes between rows reserved per
carrier while the batch is placed and routed.
"""

from typing import Any

from kohakuefda.physics.boundaries import BUS_ROOM, area_rect
from kohakuefda.physics.fabric import slots_of
from kohakuefda.solvers.lines.graph import LineGraph
from kohakuefda.solvers.lines.pack import pack_groups
from kohakuefda.solvers.lines.rows import LANE_MAX, LANE_TRIES, Box, LinesRows
from kohakuefda.solvers.lines.shape import LinesShape, room_of
from kohakulayout.errors import BudgetExhausted
from kohakulayout.ir.geometry import XY, rotate_size
from kohakulayout.physics.protocol import Anchor
from kohakulayout.solvers.structural.floorplan import Structure, item_size, world_ctx
from kohakulayout.solvers.structural.legalize import legalize

SWEEPS = 4
SIDE_CHANNEL = 2
Channel = tuple[str, str, tuple[XY, ...], str | None]


class EndfieldLines(LinesRows, LinesShape):
    """Rows by depth from the bus in groups, packed over the ports they feed."""

    def __init__(self, channel: int = 2, gap: int = 1) -> None:
        self.channel = channel
        self.gap = gap
        self._graph: LineGraph | None = None

    def graph(self, world: Any) -> LineGraph:
        if self._graph is None or self._graph.netlist is not world.problem.netlist:
            self._graph = LineGraph(world)
        return self._graph

    def initial(self, ctx: Any) -> Structure:
        """The groups' rows by depth, each row sorted under its partners until the order
        settles, every loop turned to the order that lays its group narrowest, then a
        row too wide cut and the sorting run again."""
        graph = self.graph(ctx.world)
        depth, groups, rot = graph.depths()
        structure: Structure = {
            "groups": [graph.rows_of(depth, g) for g in groups],
            "rot": rot,
        }
        structure["faces"] = self.line_faces(structure, ctx)
        for _ in range(SWEEPS * len(groups)):
            for _ in range(SWEEPS * SWEEPS):
                budgets = self.budgets(structure, ctx)
                moved = [
                    graph.reorder(
                        rows, self.group_layout(graph, rows, rot, budgets[g])[0], rot
                    )
                    for g, rows in enumerate(structure["groups"])
                ]
                if not any(moved):
                    break
            budgets = self.budgets(structure, ctx)
            for g, rows in enumerate(structure["groups"]):
                self.tune(graph, rows, rot, budgets[g])
            if not self.fold(structure, ctx):
                break
        self.refresh(structure, graph)
        return structure

    def refresh(self, structure: Structure, graph: LineGraph) -> None:
        """The flat placing order: every group's rows, side cells after their machine,
        the items a shallower row feeds first so their drops are laid first."""
        depth = {
            i: k
            for rows in structure["groups"]
            for k, row in enumerate(rows)
            for i in row
        }

        def drop(item: str) -> int:
            makers = (m for m, *_ in graph.feeds[item])
            return 0 if any(depth.get(m, 9) < depth[item] for m in makers) else 1

        structure["rows"] = [
            expanded(graph, sorted(row, key=drop))
            for rows in structure["groups"]
            for row in rows
        ]

    def tune(
        self,
        graph: LineGraph,
        rows: list[list[str]],
        rot: dict[str, int],
        budget: int | None,
    ) -> None:
        """Each belt loop of three or more along a row turned to the rotation or mirror of its order that lays the group narrowest."""
        for k, row in enumerate(rows):
            index = 0
            while index < len(row):
                loop = graph.loop_of(row[index])
                run = [i for i in row[index:] if i in loop]
                if (
                    len(run) < 3
                    or run != row[index : index + len(run)]
                    or graph.piped(row[index])
                ):
                    index += 1
                    continue

                best = (self.group_layout(graph, rows, rot, budget)[1], 0, run)
                for mirror in (run, run[::-1]):
                    for shift in range(len(run)):
                        order = mirror[shift:] + mirror[:shift]
                        rows[k] = row[:index] + order + row[index + len(run) :]
                        width = self.group_layout(graph, rows, rot, budget)[1]
                        best = min(best, (width, 1, order), key=lambda b: b[:2])
                rows[k] = row = row[:index] + best[2] + row[index + len(run) :]
                index += len(run)

    def variants(self, structure: Structure) -> list[Structure]:
        """The structure with its lanes capped at each of ``LANE_TRIES``, narrowest first."""
        return [{**structure, "lane_max": cap} for cap in LANE_TRIES]

    def laid(self, structure: Structure, ctx: Any) -> dict[str, Any]:
        """Every item's box, the lane strips in world cells, the bus parts as
        ``(part, x, y, rot)`` and every item's placed rotation. The groups are packed
        against the bus (a west group turned to read from the west face); the bus parts
        lie flat as a line over the bricks, a brick past its ends moved onto it; on a
        fixed bus each brick takes the free slot of its face nearest its box."""
        self.lane_max = structure.get("lane_max", LANE_MAX)
        world = ctx.world
        graph = self.graph(world)
        x0, y0, x1, y1 = area_rect(world.fabric)
        left, top, right, bottom = room_of(world)
        flat = [
            (p, *lying(world, p))
            for p in sorted(graph.parts, key=lambda p: item_size(world, p, 0))
        ]
        bus_y = y0 + BUS_ROOM
        if flat:
            top = bus_y + max(h for _, _, h, _ in flat)
        rot = structure["rot"]
        groups = structure["groups"]
        faces = structure.get("faces") or [None] * len(groups)
        budgets = self.budgets(structure, ctx)
        locals_ = [
            self.group_layout(graph, rows, rot, budgets[g])
            for g, rows in enumerate(groups)
        ]

        def turned(g: int, rect: Box) -> Box:
            x, y, w, h = rect
            return (y, locals_[g][1] - x - w, h, w) if faces[g] == "W" else rect

        group_of = {i: g for g, rows in enumerate(groups) for row in rows for i in row}
        lanes: dict[tuple[int, int], int] = {}
        for item, links in graph.links.items():
            for partner, *_ in links:
                a, b = group_of.get(item), group_of.get(partner)
                if a is not None and b is not None and a != b:
                    key = (min(a, b), max(a, b))
                    lanes[key] = lanes.get(key, 0) + 1

        shapes: list[list[Box]] = []
        corridors: list[list[Box]] = []
        for g, rows in enumerate(groups):
            local, _, _, bands = locals_[g]
            shape: list[Box] = []
            strips: list[Box] = []
            filled = [k for k, row in enumerate(rows) if row]
            for n, k in enumerate(filled):
                cells = [i for i in expanded(graph, rows[k]) if i in local]
                if not cells:
                    continue
                above = bands[filled[n - 1]] if n else (bands[0] if k else 0)
                below = bands[k]
                rx = min(local[i][0] for i in cells)
                ry = min(local[i][1] for i in cells)
                rw = max(local[i][0] + local[i][2] for i in cells) - rx
                rh = max(local[i][1] + local[i][3] for i in cells) - ry
                shape.append(turned(g, (rx, ry - above, rw, rh + above + below)))
                under = cells
                if n + 1 < len(filled):
                    under = [
                        i for i in expanded(graph, rows[filled[n + 1]]) if i in local
                    ]
                sx = min(rx, *(local[i][0] for i in under))
                sw = max(rx + rw, *(local[i][0] + local[i][2] for i in under)) - sx
                strips.append(turned(g, (sx, ry + rh, sw, below)))
            shapes.append(shape)
            corridors.append(strips)

        positions = pack_groups(
            shapes, faces, lanes, left, right, top, bottom, self.channel
        )
        boxes: dict[str, Box] = {}
        frames: list[Box] = []
        for g in range(len(groups)):
            local, width, height, _ = locals_[g]
            px, py = positions[g]
            for item, rect in local.items():
                x, y, w, h = turned(g, rect)
                boxes[item] = (px + x, py + y, w, h)
            _, _, w, h = turned(g, (0, 0, width, height))
            frames.append((px, py, w, h))
        rotations = {
            i: (rot.get(i, 0) + 270) % 360 if faces[g] == "W" else rot.get(i, 0)
            for i, g in group_of.items()
        }
        strips_world = [
            [(px + x, py + y, w, h) for x, y, w, h in corridors[g]]
            for g, (px, py) in enumerate(positions)
        ]

        bricks = [b for b in graph.bricks if b in boxes]
        if not flat:
            brick = max((item_size(world, b, 0)[0] for b in graph.bricks), default=0)
            free = {
                side: sorted(
                    (x, y)
                    for x, y, s in slots_of(world.fabric)
                    if s == side
                    and x0 <= x
                    and y0 <= y
                    and x + brick <= x1
                    and y + brick <= y1
                )
                for side in ("N", "W")
            }
            for brick_id in sorted(bricks, key=lambda b: boxes[b][:2]):
                face = faces[group_of[brick_id]] or "N"
                x, y, w, h = boxes.pop(brick_id)
                axis = 0 if face == "N" else 1
                near = min(
                    free.get(face, []),
                    key=lambda s: abs(s[axis] - (x, y)[axis]),
                    default=None,
                )
                if near is None:
                    continue
                free[face].remove(near)
                boxes[brick_id] = (near[0], near[1], w, h)
            bricks = [b for b in bricks if b in boxes]

        total = sum(w for _, w, _, _ in flat)
        first = min((boxes[b][0] for b in bricks), default=left)
        last = max((boxes[b][0] + boxes[b][2] for b in bricks), default=left)
        edge = min((x for x, _, _, _ in boxes.values()), default=left)
        start = min(first, max(edge, last - total))
        start = max(x0 + BUS_ROOM, min(start, x1 - BUS_ROOM - total))
        if flat:
            snap(boxes, bricks, start, start + total)
        parts = []
        for part, w, h, part_rot in flat:
            boxes[part] = (start, bus_y, w, h)
            parts.append((part, start, bus_y, part_rot))
            start += w
        return {
            "boxes": boxes,
            "frames": frames,
            "parts": parts,
            "lanes": strips_world,
            "rotations": rotations,
        }

    def channels(self, structure: Structure, ctx: Any) -> list[Channel]:
        """Per carrier, the lane under every row of every group and ``SIDE_CHANNEL``
        columns beside every group, off every group: corridors the cover keeps its
        pylons off while a pocket is free."""
        world = ctx.world
        laid = self.laid(structure, ctx)
        carriers = sorted({n.carrier for n in world.netlist.nets.values()})
        frames = laid["frames"]
        out: list[Channel] = []
        for g, (px, py, w, h) in enumerate(frames if SIDE_CHANNEL else ()):
            cells = tuple(
                (x, y)
                for y in range(py, py + h)
                for x in (
                    *range(px - SIDE_CHANNEL, px),
                    *range(px + w, px + w + SIDE_CHANNEL),
                )
                if world.in_grid((x, y))
                and not any(
                    fx <= x < fx + fw and fy <= y < fy + fh for fx, fy, fw, fh in frames
                )
            )
            for carrier in carriers:
                out.append(
                    (
                        f"side:{g}:{carrier}",
                        world.carrier_layer(carrier),
                        cells,
                        carrier,
                    )
                )
        for g, strips in enumerate(laid["lanes"]):
            for k, (x, y, w, h) in enumerate(strips):
                cells = tuple(
                    (x + dx, y + dy)
                    for dy in range(h)
                    for dx in range(w)
                    if world.in_grid((x + dx, y + dy))
                )
                for carrier in carriers:
                    out.append(
                        (
                            f"lane:{g}:{k}:{carrier}",
                            world.carrier_layer(carrier),
                            cells,
                            carrier,
                        )
                    )
        return out

    def decode(self, structure: Structure, builder: Any) -> Any:
        """Every box placed in one batch: the bus parts first, then the rows in placing order."""
        laid = self.laid(structure, world_ctx(builder))
        rotations = dict(laid["rotations"])
        order: list[str] = []
        for part, _, _, part_rot in laid["parts"]:
            order.append(part)
            rotations[part] = part_rot
        for row in structure["rows"]:
            order += [item for item in row if item not in order]
        anchors = {
            item: Anchor(
                x=laid["boxes"][item][0],
                y=laid["boxes"][item][1],
                rot=rotations.get(item, 0),
            )
            for item in order
            if item not in builder.placements and item in laid["boxes"]
        }
        return builder.place_batch(anchors)


def expanded(graph: LineGraph, row: list[str]) -> list[str]:
    """The row with each item's side cells after it."""
    return [
        cell
        for item in row
        for cell in (item, *graph.sides_of(item)["W"], *graph.sides_of(item)["E"])
    ]


def lying(world: Any, part: str) -> tuple[int, int, int]:
    """A bus part's size and rotation laid with its long side along the bus."""
    w, h = item_size(world, part, 0)
    rot = 0 if w >= h else 90
    return (*rotate_size(w, h, rot), rot)


def snap(boxes: dict[str, Box], bricks: list[str], start: int, end: int) -> None:
    """Every brick past the line's ends moved onto it, to the free place nearest the end it passed."""
    on_line = [
        (boxes[b][0], boxes[b][0] + boxes[b][2])
        for b in bricks
        if start <= boxes[b][0] and boxes[b][0] + boxes[b][2] <= end
    ]
    for brick in sorted(bricks, key=lambda b: boxes[b][0]):
        x, y, w, h = boxes[brick]
        if start <= x and x + w <= end:
            continue
        order = range(end - w, start - 1, -1) if x >= end else range(start, end - w + 1)
        for cx in order:
            if all(cx + w <= a or cx >= b for a, b in on_line):
                boxes[brick] = (cx, y, w, h)
                on_line.append((cx, cx + w))
                break


def lines_seed(ctx: Any, units: int) -> bool:
    """Legalise the lines structure's variants within ``units`` actions; whether one landed complete and valid."""
    representation = EndfieldLines()
    try:
        with ctx.budget.limit(units):
            structure = representation.initial(ctx)
            for candidate in representation.variants(structure):
                assessment = legalize(representation, candidate, ctx)
                if assessment is not None and assessment.complete and assessment.valid:
                    return True
    except BudgetExhausted:
        if ctx.budget.exhausted():
            raise
        ctx.log("lines seed used its action allocation")
    return False


__all__ = ["EndfieldLines", "expanded", "lines_seed", "snap"]
