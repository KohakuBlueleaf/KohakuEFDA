"""The geometry of the rows: columns folded from the stack, boxes from bottom-up sweeps that
align a unit over the port it feeds, bands sized by the lanes that run along them, the holds
and channels the decoder reserves."""

from itertools import combinations
from typing import Any

from kohakuefda.physics.boundaries import BRICK_KINDS, PART_KIND, area_rect
from kohakuefda.physics.facts import lane_facts
from kohakulayout.ir.geometry import XY
from kohakulayout.ir.netlist.order import flow_order
from kohakulayout.solvers.structural.floorplan import Structure, item_size
from kohakulayout.state.attach import options_at

MARGIN = 1
SWEEPS = 4
MAX_COLUMNS = 4
BEFORE_KINDS = frozenset({"outlet"})
AFTER_KINDS = frozenset({"stash", "inlet"})
SOURCE_KINDS = frozenset({"unloader", "entry"})


def stages(netlist: Any) -> dict[str, int]:
    """Each cell's stage: the longest chain of nets from a cell nothing feeds, loops cut by
    the flow order; instances count as one node over the top-level nets, so what happens
    inside a unit never orders it."""
    edges = [
        (source.cell, sink.cell)
        for net in netlist.nets.values()
        for source in net.sources
        for sink in net.sinks
        if source.cell != sink.cell
    ]
    order, loops = flow_order(list(netlist.cells), edges)
    back = set(loops)
    feeders: dict[str, set[str]] = {c: set() for c in netlist.cells}
    for source, sink in edges:
        if (source, sink) not in back:
            feeders[sink].add(source)
    stage: dict[str, int] = {}
    for cell in order:
        stage[cell] = max((stage.get(f, 0) + 1 for f in feeders[cell]), default=0)
    return {c: stage.get(c, 0) for c in netlist.cells}


def item_of(cell: str) -> str:
    """The floorplan item a world cell belongs to: its instance, or itself."""
    return cell.split("/")[0]


def pin_id_of(cell: str, pin: str) -> str:
    """The pin id a lane fact's ``cell:pin`` names: a leaf's pin is its instance's port."""
    return f"{cell.split('/')[-1]}__{pin}" if "/" in cell else pin


def partners(netlist: Any, cell_id: str, direction: str) -> list[str]:
    """The cells on the other end of the cell's nets: its consumers (``out``) or its makers (``in``)."""
    out: list[str] = []
    for net in netlist.nets.values():
        mine = net.sources if direction == "out" else net.sinks
        others = net.sinks if direction == "out" else net.sources
        if any(r.cell == cell_id for r in mine):
            out += [r.cell for r in others if r.cell != cell_id and r.cell not in out]
    return out


class RowsGeometry:
    """The geometric half of ``EndfieldRows``; mixed into it."""

    channel: int
    gap: int

    def overflow(self, structure: Structure, ctx: Any) -> int:
        """How far the boxes, with the channel under them, pass the area's right edge or
        bottom, at most; zero when they fit."""
        _, _, x1, y1 = area_rect(ctx.world.fabric)
        boxes = self.frames(structure, ctx)[0]
        wide = max((x + w - (x1 - MARGIN) for x, _, w, _ in boxes.values()), default=0)
        tall = max(
            (y + h + self.channel - (y1 - MARGIN) for _, y, _, h in boxes.values()),
            default=0,
        )
        return max(wide, tall, 0)

    def band(
        self,
        world: Any,
        structure: Structure | None = None,
        bands: list[int] | None = None,
    ) -> int:
        """The rows the bus and its bricks take above the machines: parts, bricks on both
        faces, the bus channel (the first of ``bands``, else the structure's first band,
        else the channel)."""
        netlist = world.problem.netlist
        parts = [c for c in netlist.cells.values() if c.kind == PART_KIND]
        bricks = [c for c in netlist.cells.values() if c.kind in BRICK_KINDS]

        def tall(cells: list[Any]) -> int:
            return max((item_size(world, c.id, 0)[1] for c in cells), default=0)

        sizes = bands or (structure or {}).get("bands") or [self.channel]
        return tall(parts) + 2 * tall(bricks) + max(self.channel, sizes[0])

    def bus_edge(self, world: Any) -> int:
        """The column past which the bus and its bricks reach no further, from the parts'
        first anchors; the area's left edge without parts."""
        netlist = world.problem.netlist
        edge = area_rect(world.fabric)[0]
        for cell in netlist.cells.values():
            if cell.kind != PART_KIND:
                continue
            anchor = next(iter(world.anchors(cell.id)), None)
            fp = netlist.footprint_for(cell.id)
            if anchor is None or fp is None:
                continue
            brick = max(
                (
                    item_size(world, c.id, 0)[0]
                    for c in netlist.cells.values()
                    if c.kind in BRICK_KINDS
                ),
                default=0,
            )
            edge = max(edge, anchor.x + fp.width + brick + 1)
        return edge

    def fold(self, structure: Structure, ctx: Any) -> list[list[int]]:
        """The rows' indices per column: the rows in order cut into the structure's count
        of columns; among the cuts whose columns, each as wide as its widest row, fit the
        area side by side with a channel between, the one whose tallest column (each row
        costing its height and the band under it) is the lowest, else the lowest of all.
        """
        world = ctx.world
        x0, _, x1, _ = area_rect(world.fabric)
        rows = structure["rows"]
        rot = structure["rot"]
        bands = structure.get("bands") or [self.channel] * len(rows)
        count = max(1, min(int(structure.get("columns", 1)), len(rows) or 1))
        costs = [
            max((item_size(world, i, rot.get(i, 0))[1] for i in row), default=0)
            + (bands[index + 1] if index + 1 < len(bands) else self.channel)
            for index, row in enumerate(rows)
        ]
        widths = [
            sum(item_size(world, i, rot.get(i, 0))[0] + self.gap for i in row)
            - self.gap
            for row in rows
        ]
        n = len(rows)
        if n == 0:
            return [[]]
        room = x1 - x0 - 2 * MARGIN - (count - 1) * self.channel
        best: tuple[tuple[int, int], list[list[int]]] | None = None
        for cuts in combinations(range(1, n), count - 1):
            edges = [0, *cuts, n]
            groups = [list(range(edges[i], edges[i + 1])) for i in range(count)]
            tall = max(sum(costs[i] for i in g) for g in groups)
            wide = sum(max(widths[i] for i in g) for g in groups)
            key = (int(wide > room), tall)
            if best is None or key < best[0]:
                best = (key, groups)
        return best[1] if best is not None else [list(range(n))]

    def geometry(
        self, structure: Structure, ctx: Any
    ) -> dict[str, tuple[int, int, int, int]]:
        """Each item's box; see ``frames``."""
        return self.frames(structure, ctx)[0]

    def frames(self, structure: Structure, ctx: Any) -> tuple[
        dict[str, tuple[int, int, int, int]],
        list[tuple[int, int, list[int]]],
        list[int],
    ]:
        """Each item's box, the columns as ``(left, right, rows)`` and the bands' final
        sizes: in every column the rows stacked from the bus band with the channel between
        them, the columns side by side with a vertical channel between, a column that would
        pass the right edge stacking under the last instead; the columns from bottom-up
        sweeps that align each row with the row it feeds and the row that feeds it, until a
        sweep moves nothing; a one-row band stays one row only where every drop through it
        landed aligned, else it takes a free row between its two attach rows."""
        world = ctx.world
        x0, y0, x1, _ = area_rect(world.fabric)
        rot = structure["rot"]
        rows = structure["rows"]
        folds = self.fold(structure, ctx)
        column_of = {index: c for c, members in enumerate(folds) for index in members}
        columns: list[dict[str, int]] = [{} for _ in rows]
        left = x0 + MARGIN
        for _ in range(SWEEPS):
            before = [dict(c) for c in columns]
            for index in range(len(rows) - 1, -1, -1):
                row = rows[index]
                targets: dict[str, int] = {}
                if index > 0 and column_of[index - 1] == column_of[index]:
                    targets.update(
                        self.targets(
                            ctx, row, rows[index - 1], columns[index - 1], False
                        )
                    )
                if index + 1 < len(rows) and column_of[index + 1] == column_of[index]:
                    targets.update(
                        self.targets(ctx, row, rows[index + 1], columns[index + 1])
                    )
                columns[index] = self.pack(world, row, rot, targets, left, x1 - MARGIN)
            if columns == before:
                break
        bands = list(structure.get("bands") or [self.channel] * len(rows))
        for index in range(len(rows)):
            depth = self.traffic(ctx, rows, columns, column_of, index)
            if bands[index] == 1 and column_of[max(index - 1, 0)] == column_of[index]:
                wanted = self.targets(ctx, rows[index - 1], rows[index], columns[index])
                if all(columns[index - 1][i] == x for i, x in wanted.items()):
                    continue
            bands[index] = max(self.channel, 2 + depth)
        out: dict[str, tuple[int, int, int, int]] = {}
        frames: list[tuple[int, int, list[int]]] = []
        start = left
        bus_edge = self.bus_edge(world)
        y = y0 + self.band(world, structure, bands)
        for members in folds:
            span = max(
                (columns[i][c] - left + item_size(world, c, rot.get(c, 0))[0])
                for i in members
                for c in rows[i]
            )
            if frames and start + span > x1 - MARGIN:
                start = frames[-1][0]
            elif start < bus_edge:
                y = y0 + self.band(world, structure, bands)
            else:
                y = y0 + MARGIN + max(self.channel, bands[0])
            right = start
            for index in members:
                height = 0
                for item in rows[index]:
                    w, h = item_size(world, item, rot.get(item, 0))
                    x = columns[index][item] - left + start
                    out[item] = (x, y, w, h)
                    height = max(height, h)
                    right = max(right, x + w)
                following = bands[index + 1] if index + 1 < len(bands) else self.channel
                y += height + following
            if frames and frames[-1][0] == start:
                held = frames.pop()
                frames.append((start, max(held[1], right), held[2] + list(members)))
            else:
                frames.append((start, right, list(members)))
            start = frames[-1][1] + self.channel
        return out, frames, bands

    def pack(
        self,
        world: Any,
        row: list[str],
        rot: dict[str, int],
        targets: dict[str, int],
        left: int,
        right: int,
    ) -> dict[str, int]:
        """The row's items in groups of a machine with its side cells: the aligned groups
        first, left to right by target with their machine at its target column when nothing
        stands there and the row's right edge allows it, then the others into the first gap
        that holds them."""
        netlist = world.problem.netlist
        groups: list[list[str]] = []
        pending: list[str] = []
        for item in row:
            kind = netlist.cells[item].kind
            if kind in BEFORE_KINDS:
                pending.append(item)
            elif kind in AFTER_KINDS and groups:
                groups[-1].append(item)
            else:
                groups.append([*pending, item])
                pending = []
        if pending:
            groups.append(pending)

        def size(item: str) -> int:
            return item_size(world, item, rot.get(item, 0))[0]

        def main_of(group: list[str]) -> str | None:
            return next((i for i in group if i in targets), None)

        def span_of(group: list[str]) -> int:
            return sum(size(i) + self.gap for i in group) - self.gap

        out: dict[str, int] = {}
        taken: list[tuple[int, int]] = []

        def settle(group: list[str], start: int) -> None:
            for item in group:
                out[item] = start
                start += size(item) + self.gap
            taken.append((out[group[0]], start - self.gap))
            taken.sort()

        aligned = sorted(
            (g for g in groups if main_of(g) is not None),
            key=lambda g: targets[main_of(g)],
        )
        x = left
        for group in aligned:
            main = main_of(group)
            lead = sum(size(i) + self.gap for i in group[: group.index(main)])
            want = max(x, targets[main] - lead)
            if want + span_of(group) > right:
                want = x
            settle(group, want)
            x = want + span_of(group) + self.gap
        for group in (g for g in groups if main_of(g) is None):
            span = span_of(group)
            starts = [left, *(end + self.gap for _, end in taken)]
            fits = (
                s
                for s in starts
                if s + span <= right
                and all(s + span + self.gap <= a or s >= b + self.gap for a, b in taken)
            )
            settle(group, next(fits, starts[-1]))
        return out

    def traffic(
        self,
        ctx: Any,
        rows: list[list[str]],
        columns: list[dict[str, int]],
        column_of: dict[int, int],
        index: int,
    ) -> int:
        """How many lanes run along the band above row ``index`` at its busiest column: one
        interval per lane between the x of the pin it leaves in the row above or arrives at
        in the row, and the x it comes from or goes to (the bus port, a pin in the column, or
        the column's edge toward another column), one trunk interval for a net that fans in
        or out; the deepest overlap, per carrier."""
        world = ctx.world
        netlist = world.problem.netlist
        row_of = {c: k for k, row in enumerate(rows) for c in row}
        edges: dict[int, tuple[int, int]] = {}
        for k, row in enumerate(rows):
            for item in row:
                x = columns[k][item]
                w = item_size(world, item, 0)[0]
                lo, hi = edges.get(column_of[k], (x, x + w))
                edges[column_of[k]] = (min(lo, x), max(hi, x + w))
        here = column_of.get(index, 0)

        def pin_x(cell: str, pin_id: str) -> int | None:
            item = item_of(cell)
            fp = netlist.footprint_for(item)
            pin = next((p for p in netlist.pins_of(item) if p.id == pin_id), None)
            if fp is None or pin is None:
                return None
            if item in row_of:
                return options_at(fp, pin, columns[row_of[item]][item], 0, 0)[0][1][0]
            anchor = next(iter(world.anchors(item)), None)
            if anchor is None:
                return None
            return options_at(fp, pin, anchor.x, anchor.y, anchor.rot)[0][1][0]

        def far_x(cell: str, pin_id: str) -> int | None:
            item = item_of(cell)
            if item in row_of and column_of[row_of[item]] != here:
                lo, hi = edges[here]
                return lo if column_of[row_of[item]] < here else hi
            return pin_x(cell, pin_id)

        spans: dict[str, list[tuple[int, int]]] = {}
        for net in world.netlist.nets.values():
            if "/" in net.id:
                continue
            sources = [(r, row_of.get(item_of(r.cell))) for r in net.sources]
            sinks = [(r, row_of.get(item_of(r.cell))) for r in net.sinks]
            leaving = {r.cell for r, k in sources if k == index - 1 and index > 0}
            arriving = {r.cell for r, k in sinks if k == index}
            from_bus = (
                {r.cell for r, k in sources if k is None} if index == 0 else set()
            )
            lanes = [(sc, sp, tc, tp) for (sc, sp), (tc, tp), _ in lane_facts(net)] or [
                (a.cell, a.pin, b.cell, b.pin) for a in net.sources for b in net.sinks
            ]
            pairs: list[tuple[int | None, int | None]] = []
            for sc, sp, tc, tp in lanes:
                if sc in leaving:
                    pairs.append(
                        (pin_x(sc, pin_id_of(sc, sp)), far_x(tc, pin_id_of(tc, tp)))
                    )
                elif tc in arriving:
                    pairs.append(
                        (far_x(sc, pin_id_of(sc, sp)), pin_x(tc, pin_id_of(tc, tp)))
                    )
                elif sc in from_bus:
                    pairs.append(
                        (pin_x(sc, pin_id_of(sc, sp)), pin_x(tc, pin_id_of(tc, tp)))
                    )
            known = [(a, b) for a, b in pairs if a is not None and b is not None]
            if len(net.sources) > 1 or len(net.sinks) > 1:
                xs = [x for pair in known for x in pair]
                known = [(min(xs), max(xs))] if xs else []
            for a, b in known:
                if a != b:
                    spans.setdefault(net.carrier, []).append((min(a, b), max(a, b)))
        depth = 0
        for intervals in spans.values():
            events = sorted(
                [(a, 1) for a, _ in intervals] + [(b + 1, -1) for _, b in intervals]
            )
            open_now = 0
            for _, delta in events:
                open_now += delta
                depth = max(depth, open_now)
        return depth

    def targets(
        self,
        ctx: Any,
        row: list[str],
        other: list[str],
        placed: dict[str, int],
        below: bool = True,
    ) -> dict[str, int]:
        """For each item of ``row`` the column that puts the port of its first lane to
        ``other`` over (or under) the port that lane meets there, read from the nets' lane
        facts; ``other`` is the row it feeds when ``below``, else the row feeding it."""
        world = ctx.world
        netlist = world.problem.netlist
        wanted = set(other)
        out: dict[str, int] = {}
        for item in row:
            fp = netlist.footprint_for(item)
            if fp is None:
                continue
            for net in netlist.nets.values():
                found = None
                for (sc, sp), (tc, tp), _ in lane_facts(net):
                    own, far = ((sc, sp), (tc, tp)) if below else ((tc, tp), (sc, sp))
                    if own[0].split("/")[0] == item and far[0].split("/")[0] in wanted:
                        found = (pin_id_of(*own), far[0].split("/")[0], pin_id_of(*far))
                        break
                if found is None:
                    continue
                pin_id, partner, partner_pin_id = found
                partner_fp = netlist.footprint_for(partner)
                pin = next((p for p in netlist.pins_of(item) if p.id == pin_id), None)
                partner_pin = next(
                    (p for p in netlist.pins_of(partner) if p.id == partner_pin_id),
                    None,
                )
                if partner not in placed or partner_fp is None:
                    continue
                if pin is None or partner_pin is None:
                    continue
                far_x = options_at(partner_fp, partner_pin, placed[partner], 0, 0)[0][
                    1
                ][0]
                own_x = options_at(fp, pin, 0, 0, 0)[0][1][0]
                out[item] = far_x - own_x
                break
        return out

    def channels(
        self, structure: Structure, ctx: Any
    ) -> list[tuple[str, str, tuple[XY, ...], str | None]]:
        """Per band between the rows of a column, and above its first, the channel rows for
        every carrier across that column; between columns a vertical channel."""
        world = ctx.world
        geometry, frames, sizes = self.frames(structure, ctx)
        rows = structure["rows"]
        if not any(rows):
            return []
        carriers = sorted({n.carrier for n in world.netlist.nets.values()})
        _, y0, _, y1 = area_rect(world.fabric)
        out: list[tuple[str, str, tuple[XY, ...], str | None]] = []
        bands: list[tuple[int, int, int, int]] = []
        for left, right, members in frames:
            for index in members:
                row = rows[index]
                if not row:
                    continue
                top = min(geometry[i][1] for i in row)
                bottom = max(geometry[i][1] + geometry[i][3] for i in row)
                if index == members[0]:
                    bands.append((top - sizes[0], sizes[0], left, right))
                following = sizes[index + 1] if index + 1 < len(sizes) else self.channel
                bands.append((bottom, following, left, right))
        for index, (top, size, left, right) in enumerate(bands):
            if size <= 0:
                continue
            cells = tuple(
                (x, top + dy)
                for dy in range(size)
                for x in range(left, right)
                if world.in_grid((x, top + dy))
            )
            for carrier in carriers:
                out.append(
                    (
                        f"channel:{index}:{carrier}",
                        world.carrier_layer(carrier),
                        cells,
                        carrier,
                    )
                )
        top = y0 + MARGIN
        for index, (_, right, _) in enumerate(frames[:-1]):
            cells = tuple(
                (x, y)
                for x in range(right, right + self.channel)
                for y in range(top, y1)
                if world.in_grid((x, y))
            )
            for carrier in carriers:
                out.append(
                    (
                        f"channel:column:{index}:{carrier}",
                        world.carrier_layer(carrier),
                        cells,
                        carrier,
                    )
                )
        return out

    def holds(
        self, structure: Structure, ctx: Any
    ) -> dict[str, list[tuple[str, tuple[XY, ...]]]]:
        """Per item every attach cell of every pin at its box, on the pin's layer, so no wire
        laid earlier covers a port of an item placed later."""
        world = ctx.world
        netlist = world.problem.netlist
        out: dict[str, list[tuple[str, tuple[XY, ...]]]] = {}
        for item, (x, y, _, _) in self.geometry(structure, ctx).items():
            fp = netlist.footprint_for(item)
            if fp is None:
                continue
            rot = structure["rot"].get(item, 0)
            layers: dict[str, set[XY]] = {}
            for pin in netlist.pins_of(item):
                layer = world.carrier_layer(pin.carrier)
                for _, attach, _ in options_at(fp, pin, x, y, rot):
                    if world.in_grid(attach):
                        layers.setdefault(layer, set()).add(attach)
            out[item] = [
                (layer, tuple(sorted(c))) for layer, c in sorted(layers.items())
            ]
        return out


__all__ = [
    "AFTER_KINDS",
    "BEFORE_KINDS",
    "MARGIN",
    "MAX_COLUMNS",
    "SOURCE_KINDS",
    "SWEEPS",
    "RowsGeometry",
    "item_of",
    "partners",
    "pin_id_of",
    "stages",
]
