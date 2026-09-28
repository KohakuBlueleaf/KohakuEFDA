"""Lines from the bus: the community shape as a construction on the framework's rows.

The finished lines the community shares (game-knowledge PLC-09 to PLC-13) are rows by
stage from the Depot Bus: the unloaders on the bus, one in front of each machine the
depot feeds, then each next stage one lane further; machines edge to edge when they feed
the same consumer, one cell apart otherwise so a belt from further away can pass; a lane
of one cell between rows where every belt is a drop of one cell or a short run along the
lane; outlets and inlets beside the machine they serve; a chain of its own a group of its
own, the groups side by side along the bus and on shelves below. ``EndfieldLines`` builds
that: the bus parts laid as a line along the area's top, the bricks seated in front of
their consumers, every row packed over the ports it feeds, the lanes sized by the runs
along them; the framework's decoder places it with every box and port held.
"""

import random
from fractions import Fraction
from typing import Any

from kohakuefda.physics.boundaries import BUS_ROOM, area_rect
from kohakuefda.physics.fabric import slots_of
from kohakuefda.solvers.lines_graph import LineGraph
from kohakuefda.solvers.lines_pack import pack_groups
from kohakuefda.solvers.lines_rows import LANE_MAX, LANE_TRIES, Box, LinesRows
from kohakuefda.solvers.lines_shape import LinesShape, room_of
from kohakuefda.solvers.local import EndfieldClimb
from kohakulayout.ir.geometry import XY, rotate_size
from kohakulayout.physics.protocol import Anchor
from kohakulayout.solvers import register
from kohakulayout.solvers.local.search import Trajectory
from kohakulayout.solvers.params import resolve
from kohakulayout.solvers.protocol import Param
from kohakulayout.solvers.structural import Floorplan, Rows
from kohakulayout.solvers.structural.floorplan import Structure, item_size, world_ctx
from kohakulayout.state.attach import options_at

SWEEPS = 4
POLISH_STEPS = 6000
POLISH_WEIGHTS = {
    "area": Fraction(1),
    "machines": Fraction(1),
    "length": Fraction(1, 200),
    "junctions": Fraction(1, 25),
    "bridges": Fraction(2, 25),
}
MOVES = ("swap", "shift", "flip", "reverse")
FLOOR = False
FLOOR_SLACK = 3
SIDE_CHANNEL = 2
Frame = tuple[int, int, int, int, list[list[str]]]
Part = tuple[str, int, int, int]


class EndfieldLines(LinesRows, LinesShape, Rows):
    """Rows by depth from the bus in groups, packed over the ports they feed."""

    id = "endfield.lines"

    def __init__(self, channel: int = 2, gap: int = 1, rows: int = 0) -> None:
        super().__init__(channel=channel, gap=gap, rows=rows)
        self._graph: LineGraph | None = None

    def graph(self, world: Any) -> LineGraph:
        """The netlist read once per problem."""
        if self._graph is None or self._graph.netlist is not world.problem.netlist:
            self._graph = LineGraph(world)
        return self._graph

    def refresh(self, structure: Structure, graph: LineGraph) -> None:
        """The decoder's flat rows: every group's rows, side cells beside their
        machine, the items a shallower row feeds before the others of their row so
        their drops are laid before anything runs along the lane."""
        depth = {
            i: k
            for rows in structure["groups"]
            for k, row in enumerate(rows)
            for i in row
        }

        def drop(item: str) -> int:
            return (
                0
                if any(depth.get(m, 9) < depth[item] for m, *_ in graph.feeds[item])
                else 1
            )

        structure["rows"] = [
            self.expand(graph, sorted(row, key=drop))
            for rows in structure["groups"]
            for row in rows
        ]

    def expand(self, graph: LineGraph, row: list[str]) -> list[str]:
        out: list[str] = []
        for item in row:
            sides = graph.sides_of(item)
            out += [item, *sides["W"], *sides["E"]]
        return out

    def initial(self, ctx: Any, rng: random.Random) -> Structure:
        """The groups' rows by depth, each row sorted under its partners until the
        order settles, every loop turned to the order that lays its group narrowest
        (``tune``), then a row too wide for the area cut into two and the sorting
        run again."""
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

    def tune(
        self,
        graph: LineGraph,
        rows: list[list[str]],
        rot: dict[str, int],
        budget: int | None,
    ) -> None:
        """Each belt loop along a row turned to the order, among the rotations of its
        members and their mirror, that lays the group narrowest, the order it has when
        equal; a pipe band keeps its mirrored order."""
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

    def geometry(self, structure: Structure, ctx: Any) -> dict[str, Box]:
        return self.frames(structure, ctx)[0]

    def frames(
        self, structure: Structure, ctx: Any
    ) -> tuple[dict[str, Box], list[Frame], list[Part]]:
        """Every item's box, the groups as ``(x, y, width, height, rows)`` and the bus
        parts as ``(part, x, y, rot)``; see ``laid``."""
        laid = self.laid(structure, ctx)
        return laid["boxes"], laid["frames"], laid["parts"]

    def variants(self, structure: Structure) -> list[Structure]:
        """The structure with its lanes capped at each of ``LANE_TRIES`` in turn, the narrowest first."""
        return [{**structure, "lane_max": cap} for cap in LANE_TRIES]

    def laid(self, structure: Structure, ctx: Any) -> dict[str, Any]:
        """The layout of the structure: every item's box, the groups packed against
        the bus (``pack_groups``, each row with its lanes; a west group turned to read
        from the west face), the bus parts as a line above the bricks from the first
        brick, or from the layout's left edge when the line still reaches the last
        brick from there, ports first, each laid flat, a brick past the line's ends
        moved onto it (``snap``), or on a fixed bus the bricks snapped to the
        slots of their face nearest the machines they feed, one each while the slots
        last; the lanes in world cells and the rotation every item is placed with."""
        self.lane_max = structure.get("lane_max", LANE_MAX)
        world = ctx.world
        graph = self.graph(world)
        x0, y0, x1, y1 = area_rect(world.fabric)
        left, top, right, bottom = room_of(world)
        parts = sorted(graph.parts, key=lambda p: item_size(world, p, 0))
        flat = [(p, *self.flat(world, p)) for p in parts]
        brick = max((item_size(world, b, 0)[0] for b in graph.bricks), default=0)
        slots = {
            side: sorted(
                (x, y)
                for x, y, s_ in slots_of(world.fabric)
                if s_ == side
                and x0 <= x
                and y0 <= y
                and x + brick <= x1
                and y + brick <= y1
            )
            for side in ("N", "W")
        }
        bus_y = y0 + BUS_ROOM
        if flat:
            top = bus_y + max(h for _, _, h, _ in flat)
        rot = structure["rot"]
        faces = structure.get("faces") or [None] * len(structure["groups"])
        budgets = self.budgets(structure, ctx)
        locals_ = [
            self.group_layout(graph, rows, rot, budgets[g])
            for g, rows in enumerate(structure["groups"])
        ]

        def turned(g: int, rect: Box) -> Box:
            x, y, w, h = rect
            if faces[g] != "W":
                return rect
            return (y, locals_[g][1] - x - w, h, w)

        group_of = {
            i: g
            for g, rows in enumerate(structure["groups"])
            for row in rows
            for i in row
        }
        lanes: dict[tuple[int, int], int] = {}
        for item, links in graph.links.items():
            for partner, *_ in links:
                a, b = group_of.get(item), group_of.get(partner)
                if a is not None and b is not None and a != b:
                    key = (min(a, b), max(a, b))
                    lanes[key] = lanes.get(key, 0) + 1
        shapes: list[list[Box]] = []
        corridors: list[list[Box]] = []
        for g, rows in enumerate(structure["groups"]):
            local, _, _, bands = locals_[g]
            shape: list[Box] = []
            strips: list[Box] = []
            filled = [k for k, row in enumerate(rows) if row]
            for n, k in enumerate(filled):
                cells = [i for i in self.expand(graph, rows[k]) if i in local]
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
                        i for i in self.expand(graph, rows[filled[n + 1]]) if i in local
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
        frames: list[Frame] = []
        for g, rows in enumerate(structure["groups"]):
            local, width, height, _ = locals_[g]
            px, py = positions[g]
            for item, rect in local.items():
                x, y, w, h = turned(g, rect)
                boxes[item] = (px + x, py + y, w, h)
            shown = turned(g, (0, 0, width, height))
            frames.append((px, py, shown[2], shown[3], rows))
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
            free = {side: list(cells) for side, cells in slots.items()}
            for brick_id in sorted(bricks, key=lambda b: boxes[b][:2]):
                face = faces[group_of[brick_id]] or "N"
                x, y, w, h = boxes.pop(brick_id)
                axis = 0 if face == "N" else 1
                near = min(
                    free.get(face, []),
                    key=lambda s_: abs(s_[axis] - (x, y)[axis]),
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
            self.snap(boxes, bricks, start, start + total)
        out: list[Part] = []
        for part, w, h, rot_ in flat:
            boxes[part] = (start, bus_y, w, h)
            out.append((part, start, bus_y, rot_))
            start += w
        return {
            "boxes": boxes,
            "frames": frames,
            "parts": out,
            "lanes": strips_world,
            "rotations": rotations,
        }

    @staticmethod
    def snap(boxes: dict[str, Box], bricks: list[str], start: int, end: int) -> None:
        """Every brick past the line's ends (``start`` to ``end``) moved onto it, to the free place nearest the end it passed."""
        on_line = [
            (boxes[b][0], boxes[b][0] + boxes[b][2])
            for b in bricks
            if start <= boxes[b][0] and boxes[b][0] + boxes[b][2] <= end
        ]
        for brick in sorted(bricks, key=lambda b: boxes[b][0]):
            x, y, w, h = boxes[brick]
            if start <= x and x + w <= end:
                continue
            order = (
                range(end - w, start - 1, -1) if x >= end else range(start, end - w + 1)
            )
            for cx in order:
                if all(cx + w <= a or cx >= b for a, b in on_line):
                    boxes[brick] = (cx, y, w, h)
                    on_line.append((cx, cx + w))
                    break

    def flat(self, world: Any, part: str) -> tuple[int, int, int]:
        """A part's size and rotation laid with its long side along the bus."""
        w, h = item_size(world, part, 0)
        rot = 0 if w >= h else 90
        w, h = rotate_size(w, h, rot)
        return w, h, rot

    def channels(
        self, structure: Structure, ctx: Any
    ) -> list[tuple[str, str, tuple[XY, ...], str | None]]:
        """The lane under every row of every group, per carrier, across the row above
        it and the row under it: a corridor the cover keeps its pylons off while a
        pocket is free; ``SIDE_CHANNEL`` columns beside every group's frame, off every
        frame, the same way; under ``FLOOR``, the room past every group's frame and ``FLOOR_SLACK``
        rows held on every layer, so no belt goes round below."""
        world = ctx.world
        laid = self.laid(structure, ctx)
        carriers = sorted({n.carrier for n in world.netlist.nets.values()})
        out: list[tuple[str, str, tuple[XY, ...], str | None]] = []
        if SIDE_CHANNEL:
            frames = [(px, py, w, h) for px, py, w, h, _ in laid["frames"]]
            for g, (px, py, w, h) in enumerate(frames):
                cells = tuple(
                    (x, y)
                    for y in range(py, py + h)
                    for x in (
                        *range(px - SIDE_CHANNEL, px),
                        *range(px + w, px + w + SIDE_CHANNEL),
                    )
                    if world.in_grid((x, y))
                    and not any(
                        fx <= x < fx + fw and fy <= y < fy + fh
                        for fx, fy, fw, fh in frames
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
        if FLOOR and laid["frames"]:
            left, _, right, bottom = room_of(world)
            floor = max(py + h for _, py, _, h, _ in laid["frames"]) + FLOOR_SLACK
            cells = tuple(
                (x, y)
                for y in range(floor, bottom)
                for x in range(left, right)
                if world.in_grid((x, y))
            )
            for layer in world.fabric.layers:
                out.append((f"floor:{layer}", layer, cells, None))
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

    def holds(
        self, structure: Structure, ctx: Any
    ) -> dict[str, list[tuple[str, tuple[XY, ...]]]]:
        """Per item its box on every layer its footprint takes and every attach cell of
        its pins on the pin's layer, so nothing laid earlier lands where it goes."""
        world = ctx.world
        netlist = world.problem.netlist
        graph = self.graph(world)
        laid = self.laid(structure, ctx)
        out: dict[str, list[tuple[str, tuple[XY, ...]]]] = {}
        for item, (x, y, w, h) in laid["boxes"].items():
            fp = netlist.footprint_for(item)
            if fp is None or item in graph.parts:
                continue
            layers: dict[str, set[XY]] = {}
            box = {(x + dx, y + dy) for dx in range(w) for dy in range(h)}
            for layer in world.layers_for(fp):
                layers.setdefault(layer, set()).update(box)
            for pin in netlist.pins_of(item):
                layer = world.carrier_layer(pin.carrier)
                rot = laid["rotations"].get(item, 0)
                for _, attach, _ in options_at(fp, pin, x, y, rot):
                    layers.setdefault(layer, set()).add(attach)
            out[item] = [
                (layer, tuple(sorted(c for c in cells if world.in_grid(c))))
                for layer, cells in sorted(layers.items())
            ]
        return out

    def decode(self, structure: Structure, builder: Any) -> Any:
        """The bus parts at their line first, then the rows through the framework,
        each row's machines in the order of their boxes, each followed by its side
        cells, every item at the rotation its face gives it; a brick without a box (no
        slot left for it) is left to the pack."""
        ctx = world_ctx(builder)
        laid = self.laid(structure, ctx)
        for part, x, y, rot in laid["parts"]:
            if part in builder.placements:
                continue
            refusal = builder.place(part, Anchor(x=x, y=y, rot=rot))
            if refusal is not None:
                return refusal
        boxes = laid["boxes"]
        host = self.graph(builder.world).host

        def order(item: str) -> tuple[int, int, bool, int]:
            mate = host.get(item, item)
            return (*boxes[mate][:2], item != mate, boxes[item][0])

        rows = [
            sorted((i for i in row if i in boxes), key=order)
            for row in structure["rows"]
        ]
        placed = {**structure, "rows": rows, "rot": laid["rotations"]}
        return super().decode(placed, builder)

    def mutate(self, structure: Structure, rng: random.Random) -> Structure:
        """One move drawn from ``MOVES``: two items of one row swapped; a single
        item (no brick, loop member or piped item) moved to the neighbouring row of
        its group past the bricks'; a piped item moved to the other row of its
        two-row band, turned about; a belt loop's run along its row reversed."""
        groups = [[list(row) for row in rows] for rows in structure["groups"]]
        rot = dict(structure["rot"])
        graph = self._graph
        for _ in range(8):
            move = rng.choice(MOVES)
            if move == "swap":
                rows = [row for group in groups for row in group if len(row) >= 2]
                if not rows:
                    continue
                row = rng.choice(rows)
                i, j = rng.sample(range(len(row)), 2)
                row[i], row[j] = row[j], row[i]
                break
            if graph is None:
                continue
            if move == "shift":
                spots = [
                    (group, k, item)
                    for group in groups
                    for k, row in enumerate(group)
                    for item in row
                    if k >= 1
                    and item not in graph.bricks
                    and len(graph.loop_of(item)) == 1
                    and not graph.piped(item)
                ]
                if not spots:
                    continue
                group, k, item = rng.choice(spots)
                to = k + rng.choice((-1, 1))
                if to < 1 or to >= len(group) or (to == 1 and group[0]):
                    continue
                group[k].remove(item)
                group[to].insert(rng.randrange(len(group[to]) + 1), item)
                break
            if move == "flip":
                spots = [
                    (group, k, item)
                    for group in groups
                    for k, row in enumerate(group)
                    for item in row
                    if graph.piped(item)
                    and any(
                        graph.piped(o) and rot.get(o, 0) != rot.get(item, 0)
                        for r in (k - 1, k + 1)
                        if 0 <= r < len(group)
                        for o in group[r]
                    )
                ]
                if not spots:
                    continue
                group, k, item = rng.choice(spots)
                to = next(
                    r
                    for r in (k - 1, k + 1)
                    if 0 <= r < len(group)
                    and any(
                        graph.piped(o) and rot.get(o, 0) != rot.get(item, 0)
                        for o in group[r]
                    )
                )
                group[k].remove(item)
                group[to].insert(rng.randrange(len(group[to]) + 1), item)
                rot[item] = 180 - rot.get(item, 0)
                break
            if move == "reverse":
                runs = []
                for group in groups:
                    for row in group:
                        index = 0
                        while index < len(row):
                            loop = graph.loop_of(row[index])
                            run = [i for i in row[index:] if i in loop]
                            if len(run) > 1 and run == row[index : index + len(run)]:
                                runs.append((row, index, len(run)))
                            index += max(1, len(run))
                if not runs:
                    continue
                row, index, n = rng.choice(runs)
                row[index : index + n] = row[index : index + n][::-1]
                break
        out: Structure = {
            "groups": groups,
            "rot": rot,
            "faces": list(structure.get("faces", [None] * len(groups))),
        }
        if "lane_max" in structure:
            out["lane_max"] = structure["lane_max"]
        if graph is not None:
            self.refresh(out, graph)
        return out


@register
class EndfieldLinesPlan(Floorplan):
    """The framework floorplan on ``EndfieldLines``, then the coordinate climb on the
    laid-out rows until the budget ends (``polish``); the studio's ``lines``."""

    id = "endfield.lines"
    params = (
        *(
            (
                Param(
                    name="gap",
                    type="int",
                    default=1,
                    doc="cells between the cells of a row that feed different consumers",
                )
                if p.name == "gap"
                else (
                    Param(name="until_budget", type="bool", default=False)
                    if p.name == "until_budget"
                    else p
                )
            )
            for p in Floorplan.params
        ),
        Param(
            name="polish",
            type="bool",
            default=True,
            doc="the coordinate climb from the laid-out rows until the budget ends",
        ),
    )

    def representation(self) -> Any:
        return EndfieldLines(channel=self.opts["channel"], gap=self.opts["gap"])

    def improve(self, ctx: Any) -> None:
        """The structure's climb for its ``steps``, then, under ``polish``, the project's
        coordinate climb (``EndfieldClimb``) from the best layout, moving one machine at
        a time with the wiring cost, in rounds of ``POLISH_STEPS`` proposals restarted
        from the best layout until the budget ends (one round without a budget), judged
        by ``POLISH_WEIGHTS`` (the area first, the wires and their units a hundredth of
        their usual weight)."""
        super().improve(ctx)
        if not self.opts["polish"] or ctx.best_assessment is None:
            return
        if not ctx.best_assessment.complete:
            return
        climb = EndfieldClimb()
        bounded = ctx.budget.units is not None or ctx.budget.seconds is not None
        opts = resolve(
            climb.params, {"until_budget": False, "improvement_steps": POLISH_STEPS}
        )
        objective = ctx.physics.objective
        usual = objective.weights
        objective.weights = dict(POLISH_WEIGHTS)
        ctx.frame("polish")
        try:
            ctx.restore_best()
            ctx.best_assessment = ctx.assess()
            while True:
                Trajectory(ctx, opts, climb.method, climb.search).improve()
                if not bounded:
                    break
                ctx.restore_best()
        finally:
            objective.weights = usual


__all__ = ["EndfieldLines", "EndfieldLinesPlan"]
