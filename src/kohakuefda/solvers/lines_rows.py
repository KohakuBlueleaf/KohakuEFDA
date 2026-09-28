"""The rows inside a line group: every row packed over the ports of its partners.

A group's rows are laid twice: from the deepest row up so makers spread over their
consumers, then from the bus side down so every row follows its partners on the bus
side; a row's blocks (loops as one block, everything else alone) stand at their targets
or right after the block before, edge to edge where the bus feeds them or they feed the
same consumer, with a pocket for a pylon every span; the lanes between rows are one
cell plus one per net that runs along them.
"""

from kohakuefda.solvers.lines_graph import BETWEEN_TAKERS, ENDS, LineGraph
from kohakuefda.solvers.lines_shape import room_of
from kohakulayout.solvers.structural.floorplan import item_size

Box = tuple[int, int, int, int]
LANE = 1
LANE_MAX = 3
POCKET = 2
POCKET_SPAN = 14
JUNCTION_ROWS = False
LOOP_GAP = 0
PIPE_GAP = 2
CROSSING_ROW = 1
FAR_ENDS = True
SIDE_RUNS = True
BRICK_ROOM = False
BAND_POCKETS = False
BRIDGED_DROPS = False
BETWEEN_TAKERS_ROWS = BETWEEN_TAKERS
LANE_TRIES = (2, 3)


class LinesRows:
    """The row-packing half of the lines: ``group_layout`` and what it calls."""

    gap: int
    lane_max: int = LANE_MAX

    def group_layout(
        self,
        graph: LineGraph,
        rows: list[list[str]],
        rot: dict[str, int],
        budget: int | None = None,
    ) -> tuple[dict[str, Box], int, int, list[int]]:
        """The group's boxes from its corner, its width, its height and the lane under
        each row: every row packed over the ports of its
        partners in the rows placed before it, first from the deepest row up so makers
        spread over their consumers (the bus-fed row packed as it is, edge to edge),
        then from the bus side down so every item follows
        its partners on the bus side (a row whose items all spread in the first pass
        and all have partners there moves as one, else each item on its own, one
        without partners keeping its place, a row that would carry the group past
        the ``budget`` (under ``BRICK_ROOM`` the bricks' row past the area's width
        only) moved back by the excess, no further than
        the edge of the rows placed before it on the side it sticks out, and, when
        that is not enough, packed without its targets, then without gaps or pockets
        at its targets, then without either), the bricks last over the machines they feed; the rows one lane
        apart, a lane as wide as the runs along it need."""
        world = graph.world
        left, _, right, _ = room_of(world)
        limit = budget or (right - left)
        xs: dict[str, int] = {}
        ready: set[str] = set()
        first = 1 if rows and rows[0] else 0
        aligned: set[str] = set()
        for k in range(len(rows) - 1, first - 1, -1):
            targets = self.targets(graph, rows, k, xs, rot, ready, True)
            if first and k == first:
                targets = {}
            aligned.update(targets)
            self.pack(graph, rows[k], xs, targets, rot)
            ready.update(rows[k])
        settled = dict(xs)
        ready.clear()
        for k in [*range(first, len(rows)), *range(first)]:
            targets = self.targets(graph, rows, k, xs, rot, ready, False)
            row = rows[k]
            ends = self.far_ends(graph, rows, xs, rot) if first and not k else {}
            if ends:
                kept = {
                    i: (
                        x - graph.span(i, rot.get(i, 0))[0],
                        x + sum(graph.span(i, rot.get(i, 0))[1:3]),
                    )
                    for i, x in targets.items()
                    if i not in ends
                }
                lo, hi = self.edges(graph, ready, xs, rot)
                if kept:
                    lo = min(a for a, _ in kept.values())
                    hi = max(b for _, b in kept.values())
                targets.update(self.end_targets(graph, ends, rot, lo, hi))
            if row and set(row) <= aligned and set(row) <= set(targets):
                shifts = sorted(targets[i] - settled[i] for i in row)
                shift = shifts[(len(shifts) - 1) // 2]
                targets = {i: settled[i] + shift for i in row}
            for item in row:
                targets.setdefault(item, settled.get(item, 0))
            self.pack(graph, row, xs, targets, rot)

            group = ready | (set(row) - set(ends))
            room = (right - left) if BRICK_ROOM and first and not k else limit
            if ready and self.excess(graph, group, xs, rot, room) > 0:
                lo, hi = self.edges(graph, ready, xs, rot)
                start, end = self.edges(graph, set(row), xs, rot)
                over = self.excess(graph, group, xs, rot, room)
                shift = min(lo - start, over) if start < lo else -min(end - hi, over)
                if shift:
                    targets = {i: x + shift for i, x in targets.items()}
                    self.pack(graph, row, xs, targets, rot)
            for attempt, dense in (({}, False), (targets, True), ({}, True)):
                if self.excess(graph, group, xs, rot, room) > 0:
                    self.pack(graph, row, xs, attempt, rot, dense=dense)
            ready.update(row)
        self.normalise(graph, rows, xs, rot)
        heights = [
            max((graph.span(i, rot.get(i, 0))[3] for i in row), default=0)
            for row in rows
        ]
        bands = self.bands(graph, rows, xs, rot)
        boxes: dict[str, Box] = {}
        y = bands[0] if rows and not rows[0] else 0
        for k, row in enumerate(rows):
            for item in row:
                w, h = item_size(world, item, rot.get(item, 0))
                x = xs[item]
                boxes[item] = (x, y, w, h)
                for face, columns in graph.stacks(item, rot.get(item, 0)).items():
                    for column in columns:
                        for cell, dx, dy in column:
                            cw, ch = item_size(world, cell, 0)
                            cx = x - dx - cw if face == "W" else x + w + dx
                            boxes[cell] = (cx, y + dy - ch, cw, ch)
            if row:
                y += heights[k] + bands[k]
        width = max((bx + w for bx, _, w, _ in boxes.values()), default=0)
        return boxes, width, y, bands

    @staticmethod
    def far_ends(
        graph: LineGraph,
        rows: list[list[str]],
        xs: dict[str, int],
        rot: dict[str, int],
    ) -> dict[str, float]:
        """Under ``FAR_ENDS``, the bricks whose takers all lie past the row under the bus, each with the centre of its takers along the row."""
        if not FAR_ENDS or len(rows) < 2 or not rows[0]:
            return {}
        near = set(rows[1])
        out: dict[str, float] = {}
        for brick in rows[0]:
            takers = [t for t, *_ in graph.links[brick]]
            if not takers or any(t in near or t not in xs for t in takers):
                continue
            centres = [xs[t] + graph.span(t, rot.get(t, 0))[1] / 2 for t in takers]
            out[brick] = sum(centres) / len(centres)
        return out

    @staticmethod
    def end_targets(
        graph: LineGraph, ends: dict[str, float], rot: dict[str, int], lo: int, hi: int
    ) -> dict[str, int]:
        """The far bricks' targets outside the bricks their row aligns (``lo`` to ``hi``, the rows' edges when it aligns none): the half with the lower taker centres left of ``lo``, nearest first, the rest right of ``hi``, an odd middle one on the side its centre lies."""
        ranked = sorted(ends, key=lambda i: ends[i])
        half = len(ranked) // 2
        if len(ranked) % 2 and ends[ranked[half]] <= (lo + hi) / 2:
            half += 1
        out: dict[str, int] = {}
        x = lo
        for brick in reversed(ranked[:half]):
            lead, w, trail, _ = graph.span(brick, rot.get(brick, 0))
            x -= lead + w + trail
            out[brick] = x + lead
        x = hi
        for brick in ranked[half:]:
            lead, w, trail, _ = graph.span(brick, rot.get(brick, 0))
            out[brick] = x + lead
            x += lead + w + trail
        return out

    @staticmethod
    def edges(
        graph: LineGraph, items: set[str], xs: dict[str, int], rot: dict[str, int]
    ) -> tuple[int, int]:
        """The leftmost and rightmost cell edge of the items with their side cells."""
        lo = min((xs[i] - graph.span(i, rot.get(i, 0))[0] for i in items), default=0)
        hi = max(
            (xs[i] + sum(graph.span(i, rot.get(i, 0))[1:3]) for i in items), default=0
        )
        return lo, hi

    def excess(
        self,
        graph: LineGraph,
        items: set[str],
        xs: dict[str, int],
        rot: dict[str, int],
        limit: int,
    ) -> int:
        """How far the items' width passes ``limit``."""
        lo, hi = self.edges(graph, items, xs, rot)
        return hi - lo - limit

    def pack(
        self,
        graph: LineGraph,
        row: list[str],
        xs: dict[str, int],
        targets: dict[str, int],
        rot: dict[str, int],
        dense: bool = False,
    ) -> None:
        """The row's blocks (a belt loop's members as one block, in pairs edge to edge
        with ``LOOP_GAP`` at most between pairs, a pipe band's members as one block
        ``PIPE_GAP`` apart, every other item alone) with a target in target order, each
        at its target when the
        block before leaves room, else right after it, siblings, bricks and every block
        of a bus-fed row edge to edge, ``gap`` cells otherwise, ``PIPE_GAP`` between two
        piped items, one beside a single one, and a pocket of ``POCKET`` cells for a
        pylon, plus that clearance, before the block that would carry the row past
        ``POCKET_SPAN`` since the last; then the blocks without a target, in row order,
        each into the gap (an end counts) that holds it nearest its partners' centre,
        else the first from the left, a row without targets with the same pockets, the
        first half a span in on a bus-fed row so neighbouring rows' pylons fall out of
        step; then, under ``ENDS``, the row's guests (``LineGraph.guests``) without a
        target at the end nearest their partners; ``dense``: no gaps or pockets."""
        tight = dense or any(graph.fed_by_bus(i) and not graph.piped(i) for i in row)
        inner = 0 if tight else self.gap
        span_limit = 10**9 if dense else POCKET_SPAN
        spans = {i: graph.span(i, rot.get(i, 0)) for i in row}
        blocks: list[list[str]] = []
        index = 0
        while index < len(row):
            loop = graph.loop_of(row[index])
            run = [i for i in row[index:] if i in loop]
            if len(run) > 1 and run == row[index : index + len(run)]:
                blocks.append(run)
            else:
                blocks.append([row[index]])
            index += len(blocks[-1])

        pockets: dict[int, set[int]] = {}

        def between(block: list[str], n: int) -> int:
            """The gap before the block's ``n``th member: ``PIPE_GAP`` before one that carries pipes, plus a pocket under ``BAND_POCKETS`` before the member that would carry a piped block past ``POCKET_SPAN`` since the last, ``LOOP_GAP`` at most before an odd one."""
            if graph.piped(block[n]):
                key = id(block)
                if key not in pockets:
                    marks: set[int] = set()
                    filled = sum(spans[block[0]][:3])
                    for m in range(1, len(block)):
                        need = sum(spans[block[m]][:3])
                        if BAND_POCKETS and filled + PIPE_GAP + need > span_limit:
                            marks.add(m)
                            filled = 0
                        else:
                            filled += PIPE_GAP
                        filled += need
                    pockets[key] = marks
                return PIPE_GAP + (POCKET if n in pockets[key] else 0)
            return min(inner, LOOP_GAP) if n % 2 else 0

        def width(block: list[str]) -> int:
            total = sum(spans[i][1] for i in block)
            total += sum(spans[i][2] for i in block[:-1])
            total += sum(between(block, n) for n in range(1, len(block)))
            return total + sum(spans[i][0] for i in block[1:])

        guests = graph.guests(row, rot) if ENDS else []
        if BETWEEN_TAKERS_ROWS:
            guests = [i for i in guests if i not in targets]

        def settle(block: list[str], x: int) -> None:
            for n, i in enumerate(block):
                xs[i] = x
                if n + 1 < len(block):
                    x += spans[i][1] + spans[i][2] + spans[block[n + 1]][0]
                    x += between(block, n + 1)

        aligned = sorted(
            (b for b in blocks if b[0] in targets and b[0] not in guests),
            key=lambda b: (targets[b[0]], row.index(b[0])),
        )
        taken: list[tuple[int, int]] = []
        cursor: int | None = None
        filled = 0
        for item in row:
            xs.pop(item, None)
        for index, block in enumerate(aligned):
            lead, trail = spans[block[0]][0], spans[block[-1]][2]
            want = targets[block[0]]
            x = want if cursor is None else max(cursor + lead, want)
            settle(block, x)
            gap = self.gap
            if tight or (
                index + 1 < len(aligned)
                and (
                    graph.siblings(block[-1], aligned[index + 1][0])
                    or block[-1] in graph.bricks
                )
            ):
                gap = 0
            if index + 1 < len(aligned):
                gap = max(gap, self.clearance(graph, block[-1], aligned[index + 1][0]))
            filled += lead + width(block) + trail
            if index + 1 < len(aligned) and block[-1] not in graph.bricks:
                ahead = sum(spans[aligned[index + 1][0]][:3])
                if filled + gap + ahead > span_limit:
                    pocket = POCKET + self.clearance(
                        graph, block[-1], aligned[index + 1][0]
                    )
                    gap, filled = max(gap, pocket), 0
                else:
                    filled += gap
            taken.append((x - lead, x + width(block) + trail))
            cursor = x + width(block) + trail + gap
        loose = [b for b in blocks if b[0] not in targets and b[0] not in guests]
        filled = POCKET_SPAN // 2 if tight else 0
        for index, block in enumerate(loose):
            lead, trail = spans[block[0]][0], spans[block[-1]][2]
            need = lead + width(block) + trail
            if not targets and index and filled + need > span_limit:
                taken[-1] = (taken[-1][0], taken[-1][1] + POCKET)
                filled = 0
            filled += need
            apart = max(inner, self.clearance(graph, block[0], *row))
            starts = sorted({0, *(end + apart for _, end in taken)})
            if taken:
                starts.append(min(a for a, _ in taken) - apart - need)
            free = [
                s_
                for s_ in starts
                if all(s_ + need + apart <= a or s_ >= b + apart for a, b in taken)
            ]
            near = self.partners_centre(graph, block, row, xs)
            if near is None or not free:
                found = next((s_ for s_ in free if s_ >= 0), starts[-1])
            else:
                found = min(free, key=lambda s_: (abs(s_ + need / 2 - near), s_))
            settle(block, found + lead)
            taken.append((found, found + need))
            taken.sort()
        for item in guests:
            lead, w, trail, _ = spans[item]
            need = lead + w + trail
            near = self.partners_centre(graph, [item], row, xs)
            lo = min((a for a, _ in taken), default=0)
            hi = max((b for _, b in taken), default=0)
            at_left = near is None or abs(lo - near) <= abs(hi - near)
            found = lo - inner - need if at_left else hi + inner
            settle([item], found + lead)
            taken.append((found, found + need))
            taken.sort()

    @staticmethod
    def piped_pair(graph: LineGraph, a: str, b: str) -> bool:
        """Whether both items carry pipes, so their facing pipe ports need attach cells of their own between them."""
        return graph.piped(a) and graph.piped(b)

    @staticmethod
    def clearance(graph: LineGraph, item: str, *others: str) -> int:
        """The cells to keep between the item and its neighbour: ``PIPE_GAP`` when both carry pipes, one when either does (a pipe port attaches beside its item), else none."""
        piped = graph.piped(item)
        beside = [graph.piped(o) for o in others if o != item]
        if piped and any(beside):
            return PIPE_GAP
        return 1 if piped or any(beside) else 0

    @staticmethod
    def partners_centre(
        graph: LineGraph, block: list[str], row: list[str], xs: dict[str, int]
    ) -> float | None:
        """The mean centre of the block's makers and takers already placed along its row; ``None`` without any."""
        centres: list[float] = []
        for item in block:
            partners = [p for p, *_ in graph.links[item]]
            partners += [m for m, *_ in graph.feeds[item]]
            for other in partners:
                if other in row and other in xs and other not in block:
                    centres.append(xs[other] + graph.span(other)[1] / 2)
        return sum(centres) / len(centres) if centres else None

    def normalise(
        self,
        graph: LineGraph,
        rows: list[list[str]],
        xs: dict[str, int],
        rot: dict[str, int],
    ) -> None:
        """Every row shifted together so the group's leftmost cell edge is at zero."""
        edge = min(
            (xs[i] - graph.span(i, rot.get(i, 0))[0] for row in rows for i in row),
            default=0,
        )
        for row in rows:
            for item in row:
                xs[item] -= edge

    def targets(
        self,
        graph: LineGraph,
        rows: list[list[str]],
        k: int,
        xs: dict[str, int],
        rot: dict[str, int],
        ready: set[str],
        deeper: bool,
    ) -> dict[str, int]:
        """For each item of row ``k`` the x that puts the port of its lane over the
        partner's port: the lower median over its consumers among the ``ready`` items
        of other rows when the ready rows are the ``deeper`` ones, else over its
        makers there and then its consumers, the partners that share the item with
        nothing else in its row counting alone when it has any; under
        ``BETWEEN_TAKERS`` on the bus-side pass a turned single whose takers all
        stand in its row with targets, the centre between them; a loop as one block;
        else right after its maker along the row."""
        out: dict[str, int] = {}
        mine = set(rows[k])
        for item in rows[k]:
            wants: list[int] = []
            sides = (
                (graph.links[item],)
                if deeper
                else (graph.feeds[item], graph.links[item])
            )
            for links in sides:
                found = [
                    link for link in links if link[0] in ready and link[0] not in mine
                ]
                own = [link for link in found if graph.exclusive(item, link, mine)]
                wants = [graph.aligned(item, link, xs, rot) for link in own or found]
                if wants:
                    break
            if wants:
                out[item] = sorted(wants)[(len(wants) - 1) // 2]
        if BETWEEN_TAKERS_ROWS and not deeper:
            for item in rows[k]:
                takers = [t for t, *_ in graph.links[item]]
                if (
                    item in out
                    or not takers
                    or rot.get(item, 0) != 180
                    or len(graph.loop_of(item)) > 1
                    or not all(t in mine and t in out for t in takers)
                ):
                    continue
                centres = [out[t] + graph.span(t, rot.get(t, 0))[1] / 2 for t in takers]
                out[item] = round(
                    sum(centres) / len(centres)
                    - graph.span(item, rot.get(item, 0))[1] / 2
                )
        out = self.blocked(graph, rows[k], out, rot)
        for index, item in enumerate(rows[k]):
            if item in out or len(graph.loop_of(item)) > 1:
                continue
            before = rows[k][:index]
            along = [m for m, *_ in graph.feeds[item] if m in before and m in xs]
            for maker in along[:1]:
                _, w, trail, _ = graph.span(maker, rot.get(maker, 0))
                out[item] = xs[maker] + w + trail + self.gap
                out[item] += graph.span(item, rot.get(item, 0))[0]
        return self.centred(graph, rows[k], out, rot)

    def blocked(
        self,
        graph: LineGraph,
        row: list[str],
        targets: dict[str, int],
        rot: dict[str, int],
    ) -> dict[str, int]:
        """The targets with every loop along the row packed as one block: the block
        starts at the lower median of what its members want, each read back to the
        block's start, and every member wants its place in the block."""
        out = dict(targets)
        index = 0
        while index < len(row):
            loop = graph.loop_of(row[index])
            run = [i for i in row[index:] if i in loop]
            if len(run) > 1 and run == row[index : index + len(run)]:
                offset = 0
                wants: list[int] = []
                offsets: dict[str, int] = {}
                for item in run:
                    lead, w, trail, _ = graph.span(item, rot.get(item, 0))
                    offsets[item] = offset
                    if item in targets:
                        wants.append(targets[item] - offset)
                    offset += lead + w + trail + self.gap
                if wants:
                    start = sorted(wants)[(len(wants) - 1) // 2]
                    for item in run:
                        out[item] = start + offsets[item]
                index += len(run)
            else:
                index += 1
        return out

    def centred(
        self,
        graph: LineGraph,
        row: list[str],
        targets: dict[str, int],
        rot: dict[str, int],
    ) -> dict[str, int]:
        """The targets with every run of siblings wanting one x spread about it: the
        run starts half its width before the x the first sibling wants."""
        out = dict(targets)
        index = 0
        while index < len(row):
            run = [row[index]]
            while (
                index + len(run) < len(row)
                and graph.siblings(run[-1], row[index + len(run)])
                and targets.get(run[-1]) == targets.get(row[index + len(run)])
            ):
                run.append(row[index + len(run)])
            if len(run) > 1 and run[0] in targets:
                spans = [graph.span(i, rot.get(i, 0)) for i in run]
                width = sum(lead + w + trail for lead, w, trail, _ in spans)
                out[run[0]] = targets[run[0]] - (width - spans[0][1]) // 2
            index += len(run)
        return out

    def bands(
        self,
        graph: LineGraph,
        rows: list[list[str]],
        xs: dict[str, int],
        rot: dict[str, int],
    ) -> list[int]:
        """The lane under each row: ``LANE`` cells at least, one per run along it
        at its busiest column per carrier, and when a drop stands strictly inside a
        run the drops' ``LANE`` cells and ``CROSSING_ROW`` more on top of the runs'
        (a run crosses a drop on a row of its own; under ``BRIDGED_DROPS`` it bridges
        the drop, LOG-11, and the lane is its runs' depth), at most ``lane_max`` (the solver tries the caps of
        ``LANE_TRIES`` narrowest first), never fewer than a multi-pin face needs (one
        per two pins past the first). A maker facing the bus emits into the lane under
        its row, a turned one into the lane above; a taker reads the other way round; a
        pipe between two items of one row takes no lane; a belt whose two pins share a
        lane runs along it between their nearest ports, none when their ports overlap
        (``JUNCTION_ROWS``: a pin carrying another belt still takes a row); a belt from
        or to another group runs along its pin's lane to the row's nearer end, so does
        one between farther rows at both ends; a net's touching runs count as one."""
        row_of = {i: k for k, row in enumerate(rows) for i in row}
        spans: list[dict[tuple[str, str], list[tuple[int, int]]]] = [{} for _ in rows]
        drops: list[set[int]] = [set() for _ in rows]

        def add(lane: int, key: tuple[str, str], run: tuple[int, int]) -> None:
            """The run into the lane's runs of its net, joined with those it touches."""
            lo, hi = min(run), max(run)
            kept: list[tuple[int, int]] = []
            for a, b in spans[lane].get(key, []):
                if a <= hi + 1 and lo <= b + 1:
                    lo, hi = min(lo, a), max(hi, b)
                else:
                    kept.append((a, b))
            spans[lane][key] = [*kept, (lo, hi)]

        def emits(item: str) -> int:
            return row_of[item] - (1 if rot.get(item, 0) == 180 else 0)

        def reads(item: str) -> int:
            return row_of[item] - (0 if rot.get(item, 0) == 180 else 1)

        fans: dict[tuple[str, str], int] = {}
        for item, links in graph.links.items():
            for partner, own, far, _, _ in links:
                fans[(item, own)] = fans.get((item, own), 0) + 1
                fans[(partner, far)] = fans.get((partner, far), 0) + 1
        edges = {
            k: (
                min(xs[i] - graph.span(i, rot.get(i, 0))[0] for i in row),
                max(xs[i] + sum(graph.span(i, rot.get(i, 0))[1:3]) for i in row),
            )
            for k, row in enumerate(rows)
            if row
        }

        def outward(item: str, pin: str, lane: int, carrier: str, net: str) -> None:
            """A belt from or to another group runs along the pin's lane to the row's
            nearer end; from an item at the row's end it leaves down the side and takes
            no run (``SIDE_RUNS``)."""
            if SIDE_RUNS and item in (rows[row_of[item]][0], rows[row_of[item]][-1]):
                return
            lo, hi = graph.port_range(item, pin, rot.get(item, 0))
            lo, hi = lo + xs[item], hi + xs[item]
            left, right = edges[row_of[item]]
            run = (left, lo) if lo - left <= right - hi else (hi, right)
            if 0 <= lane < len(spans):
                add(lane, (carrier, net), run)

        for item, links in graph.feeds.items():
            if item in row_of:
                for partner, own, far, carrier, net in links:
                    if partner not in row_of:
                        outward(item, own, reads(item), carrier, net)
        for item, links in graph.links.items():
            if item not in row_of:
                continue
            for partner, own, far, carrier, net in links:
                if partner not in row_of:
                    outward(item, own, emits(item), carrier, net)
                    continue
                alo, ahi = graph.port_range(item, own, rot.get(item, 0))
                blo, bhi = graph.port_range(partner, far, rot.get(partner, 0))
                alo, ahi = alo + xs[item], ahi + xs[item]
                blo, bhi = blo + xs[partner], bhi + xs[partner]
                first, last = emits(item), reads(partner)
                if carrier == "pipe" and row_of[item] == row_of[partner]:
                    continue
                if first != last:
                    outward(item, own, first, carrier, net)
                    outward(partner, far, last, carrier, net)
                    continue
                shared = JUNCTION_ROWS and (
                    fans[(item, own)] > 1 or fans[(partner, far)] > 1
                )
                if alo <= bhi and blo <= ahi and not shared:
                    drops[first].update(range(max(alo, blo), min(ahi, bhi) + 1))
                    continue
                run = (
                    (ahi, blo)
                    if ahi < blo
                    else (bhi, alo) if bhi < alo else (min(alo, blo), max(ahi, bhi))
                )
                add(first, (carrier, net), run)
        pins: list[dict[str, set[str]]] = [{} for _ in rows]
        for item, links in graph.links.items():
            if item in row_of and 0 <= emits(item) < len(rows):
                for _, own, *_ in links:
                    pins[emits(item)].setdefault(item, set()).add(own)
        for item, links in graph.feeds.items():
            if item in row_of and 0 <= reads(item) < len(rows):
                for _, own, *_ in links:
                    pins[reads(item)].setdefault(item, set()).add(own)
        out: list[int] = []
        for k, runs in enumerate(spans):
            intervals = [
                (carrier, net, lo, hi)
                for (carrier, net), pairs in runs.items()
                for lo, hi in pairs
            ]
            fan = max((1 + (len(p) - 1) // 2 for p in pins[k].values()), default=1)
            depth = 0
            for carrier in {c for c, *_ in intervals}:
                events = sorted(
                    [(lo, 1) for c, _, lo, _ in intervals if c == carrier]
                    + [(hi + 1, -1) for c, _, _, hi in intervals if c == carrier]
                )
                open_now = 0
                for _, delta in events:
                    open_now += delta
                    depth = max(depth, open_now)
            crossed = any(
                any(lo < col < hi for col in drops[k]) for _, _, lo, hi in intervals
            )
            wide = LANE + depth + CROSSING_ROW if crossed else max(LANE, depth)
            if BRIDGED_DROPS:
                wide = max(LANE, depth)
            wide = min(wide, self.lane_max)
            out.append(max(wide, fan))
        return out


__all__ = [
    "BAND_POCKETS",
    "BETWEEN_TAKERS_ROWS",
    "BRICK_ROOM",
    "BRIDGED_DROPS",
    "CROSSING_ROW",
    "FAR_ENDS",
    "JUNCTION_ROWS",
    "LANE",
    "LANE_MAX",
    "LANE_TRIES",
    "LOOP_GAP",
    "PIPE_GAP",
    "POCKET",
    "POCKET_SPAN",
    "SIDE_RUNS",
    "Box",
    "LinesRows",
]
