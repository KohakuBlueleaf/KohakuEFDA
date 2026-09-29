"""The rows inside a lines group: every row packed over the ports of its partners.

A group's rows are laid from the deepest row up so makers spread over their consumers,
then from the bus down so every row follows its partners there; a row's blocks (a loop
as one block) stand at their targets or right after the block before, with a pocket for
a pylon every span; the lane under a row is as wide as the runs along it.
"""

from kohakuefda.solvers.lines.graph import LineGraph
from kohakuefda.solvers.lines.shape import room_of
from kohakulayout.solvers.structural.floorplan import item_size

Box = tuple[int, int, int, int]
LANE = 1
LANE_MAX = 3
LANE_TRIES = (2, 3)
POCKET = 2
POCKET_SPAN = 14
LOOP_GAP = 0
PIPE_GAP = 2
CROSSING_ROW = 1


class LinesRows:
    """The row-packing half of ``EndfieldLines``: ``group_layout`` and what it calls."""

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
        each row. The second pass moves a row as one when all its items aligned in the
        first; a row that carries the group past ``budget`` moves back by the excess,
        then packs without targets, then dense at its targets, then dense; the bricks
        whose takers all lie past the row under the bus go outside the aligned bricks.
        """
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
            ends = far_ends(graph, rows, xs, rot) if first and not k else {}
            if ends:
                kept = {
                    i: span_edges(graph, i, x, rot)
                    for i, x in targets.items()
                    if i not in ends
                }
                lo, hi = edges(graph, ready, xs, rot)
                if kept:
                    lo = min(a for a, _ in kept.values())
                    hi = max(b for _, b in kept.values())
                targets.update(end_targets(graph, ends, rot, lo, hi))
            if row and set(row) <= aligned and set(row) <= set(targets):
                shifts = sorted(targets[i] - settled[i] for i in row)
                shift = shifts[(len(shifts) - 1) // 2]
                targets = {i: settled[i] + shift for i in row}
            for item in row:
                targets.setdefault(item, settled.get(item, 0))
            self.pack(graph, row, xs, targets, rot)

            group = ready | (set(row) - set(ends))
            if ready and excess(graph, group, xs, rot, limit) > 0:
                lo, hi = edges(graph, ready, xs, rot)
                start, end = edges(graph, set(row), xs, rot)
                over = excess(graph, group, xs, rot, limit)
                shift = min(lo - start, over) if start < lo else -min(end - hi, over)
                if shift:
                    targets = {i: x + shift for i, x in targets.items()}
                    self.pack(graph, row, xs, targets, rot)
            for attempt, dense in (({}, False), (targets, True), ({}, True)):
                if excess(graph, group, xs, rot, limit) > 0:
                    self.pack(graph, row, xs, attempt, rot, dense=dense)
            ready.update(row)

        normalise(graph, rows, xs, rot)
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

    def pack(
        self,
        graph: LineGraph,
        row: list[str],
        xs: dict[str, int],
        targets: dict[str, int],
        rot: dict[str, int],
        dense: bool = False,
    ) -> None:
        """The row's blocks with a target in target order, each at its target or right
        after the block before (edge to edge for siblings, bricks and a bus-fed row,
        ``gap`` otherwise, pipe clearance, a ``POCKET`` every ``POCKET_SPAN``); then
        the blocks without a target into the gap nearest their partners; then the
        guests at the end nearest their partners. ``dense``: no gaps or pockets."""
        tight = dense or any(graph.fed_by_bus(i) and not graph.piped(i) for i in row)
        inner = 0 if tight else self.gap
        span_limit = 10**9 if dense else POCKET_SPAN
        spans = {i: graph.span(i, rot.get(i, 0)) for i in row}
        blocks: list[list[str]] = []
        index = 0
        while index < len(row):
            loop = graph.loop_of(row[index])
            run = [i for i in row[index:] if i in loop]
            whole = len(run) > 1 and run == row[index : index + len(run)]
            blocks.append(run if whole else [row[index]])
            index += len(blocks[-1])

        def between(block: list[str], n: int) -> int:
            if graph.piped(block[n]):
                return PIPE_GAP
            return min(inner, LOOP_GAP) if n % 2 else 0

        def width(block: list[str]) -> int:
            total = sum(spans[i][1] for i in block)
            total += sum(spans[i][2] for i in block[:-1])
            total += sum(between(block, n) for n in range(1, len(block)))
            return total + sum(spans[i][0] for i in block[1:])

        def settle(block: list[str], x: int) -> None:
            for n, i in enumerate(block):
                xs[i] = x
                if n + 1 < len(block):
                    x += spans[i][1] + spans[i][2] + spans[block[n + 1]][0]
                    x += between(block, n + 1)

        guests = graph.guests(row, rot)
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
            following = aligned[index + 1][0] if index + 1 < len(aligned) else None
            gap = self.gap
            if tight or (
                following is not None
                and (graph.siblings(block[-1], following) or block[-1] in graph.bricks)
            ):
                gap = 0
            if following is not None:
                gap = max(gap, clearance(graph, block[-1], following))
            filled += lead + width(block) + trail
            if following is not None and block[-1] not in graph.bricks:
                ahead = sum(spans[following][:3])
                if filled + gap + ahead > span_limit:
                    pocket = POCKET + clearance(graph, block[-1], following)
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
            apart = max(inner, clearance(graph, block[0], *row))
            starts = sorted({0, *(end + apart for _, end in taken)})
            if taken:
                starts.append(min(a for a, _ in taken) - apart - need)
            free = [
                s
                for s in starts
                if all(s + need + apart <= a or s >= b + apart for a, b in taken)
            ]
            near = partners_centre(graph, block, row, xs)
            if near is None or not free:
                found = next((s for s in free if s >= 0), starts[-1])
            else:
                found = min(free, key=lambda s: (abs(s + need / 2 - near), s))
            settle(block, found + lead)
            taken.append((found, found + need))
            taken.sort()

        for item in guests:
            lead, w, trail, _ = spans[item]
            need = lead + w + trail
            near = partners_centre(graph, [item], row, xs)
            lo = min((a for a, _ in taken), default=0)
            hi = max((b for _, b in taken), default=0)
            at_left = near is None or abs(lo - near) <= abs(hi - near)
            found = lo - inner - need if at_left else hi + inner
            settle([item], found + lead)
            taken.append((found, found + need))
            taken.sort()

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
        """For each item of row ``k`` the x that puts its lane's port over the
        partner's: the lower median over its consumers among the ``ready`` rows when
        they are ``deeper``, else over its makers and then its consumers (exclusive
        partners alone when it has any); a loop as one block; else right after its
        maker along the row; sibling runs centred."""
        out: dict[str, int] = {}
        mine = set(rows[k])
        for item in rows[k]:
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
                    out[item] = sorted(wants)[(len(wants) - 1) // 2]
                    break

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
        return centred(graph, rows[k], out, rot)

    def blocked(
        self,
        graph: LineGraph,
        row: list[str],
        targets: dict[str, int],
        rot: dict[str, int],
    ) -> dict[str, int]:
        """The targets with every loop along the row as one block starting at the lower median of what its members want."""
        out = dict(targets)
        index = 0
        while index < len(row):
            loop = graph.loop_of(row[index])
            run = [i for i in row[index:] if i in loop]
            if len(run) < 2 or run != row[index : index + len(run)]:
                index += 1
                continue

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
        return out

    def bands(
        self,
        graph: LineGraph,
        rows: list[list[str]],
        xs: dict[str, int],
        rot: dict[str, int],
    ) -> list[int]:
        """The lane under each row: ``LANE`` cells at least, one per run along it at its
        busiest column per carrier, ``CROSSING_ROW`` more where a run crosses a drop,
        at most ``lane_max``, never fewer than a multi-pin face needs. A maker facing
        the bus emits into the lane under its row, a turned one into the lane above; a
        belt between two pins of one lane runs between their nearest ports unless the
        ports overlap; a belt to another group or row runs to the row's nearer end
        unless its item stands at the row's end."""
        row_of = {i: k for k, row in enumerate(rows) for i in row}
        spans: list[dict[tuple[str, str], list[tuple[int, int]]]] = [{} for _ in rows]
        drops: list[set[int]] = [set() for _ in rows]

        def add(lane: int, key: tuple[str, str], run: tuple[int, int]) -> None:
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

        ends = {k: edges(graph, set(row), xs, rot) for k, row in enumerate(rows) if row}

        def outward(item: str, pin: str, lane: int, carrier: str, net: str) -> None:
            if item in (rows[row_of[item]][0], rows[row_of[item]][-1]):
                return
            lo, hi = graph.port_range(item, pin, rot.get(item, 0))
            lo, hi = lo + xs[item], hi + xs[item]
            left, right = ends[row_of[item]]
            run = (left, lo) if lo - left <= right - hi else (hi, right)
            if 0 <= lane < len(spans):
                add(lane, (carrier, net), run)

        for item, links in graph.feeds.items():
            if item in row_of:
                for partner, own, _, carrier, net in links:
                    if partner not in row_of:
                        outward(item, own, reads(item), carrier, net)

        for item, links in graph.links.items():
            if item not in row_of:
                continue
            for partner, own, far, carrier, net in links:
                if partner not in row_of:
                    outward(item, own, emits(item), carrier, net)
                    continue
                first, last = emits(item), reads(partner)
                if carrier == "pipe" and row_of[item] == row_of[partner]:
                    continue
                if first != last:
                    outward(item, own, first, carrier, net)
                    outward(partner, far, last, carrier, net)
                    continue

                alo, ahi = graph.port_range(item, own, rot.get(item, 0))
                blo, bhi = graph.port_range(partner, far, rot.get(partner, 0))
                alo, ahi = alo + xs[item], ahi + xs[item]
                blo, bhi = blo + xs[partner], bhi + xs[partner]
                if alo <= bhi and blo <= ahi:
                    drops[first].update(range(max(alo, blo), min(ahi, bhi) + 1))
                    continue
                run = (
                    (ahi, blo)
                    if ahi < blo
                    else (bhi, alo) if bhi < alo else (min(alo, blo), max(ahi, bhi))
                )
                add(first, (carrier, net), run)

        pins: list[dict[str, set[str]]] = [{} for _ in rows]
        for lanes_of, mapping in ((emits, graph.links), (reads, graph.feeds)):
            for item, links in mapping.items():
                if item in row_of and 0 <= lanes_of(item) < len(rows):
                    for _, own, *_ in links:
                        pins[lanes_of(item)].setdefault(item, set()).add(own)

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
            out.append(max(min(wide, self.lane_max), fan))
        return out


def span_edges(graph: LineGraph, item: str, x: int, rot: dict[str, int]) -> tuple:
    """The item's left and right cell edge, side cells included, standing at ``x``."""
    lead, w, trail, _ = graph.span(item, rot.get(item, 0))
    return x - lead, x + w + trail


def edges(
    graph: LineGraph, items: set[str], xs: dict[str, int], rot: dict[str, int]
) -> tuple[int, int]:
    """The leftmost and rightmost cell edge of the items with their side cells."""
    spans = [span_edges(graph, i, xs[i], rot) for i in items]
    return min((a for a, _ in spans), default=0), max((b for _, b in spans), default=0)


def excess(
    graph: LineGraph,
    items: set[str],
    xs: dict[str, int],
    rot: dict[str, int],
    limit: int,
) -> int:
    lo, hi = edges(graph, items, xs, rot)
    return hi - lo - limit


def normalise(
    graph: LineGraph, rows: list[list[str]], xs: dict[str, int], rot: dict[str, int]
) -> None:
    """Every row shifted together so the group's leftmost cell edge is at zero."""
    edge = edges(graph, {i for row in rows for i in row}, xs, rot)[0]
    for row in rows:
        for item in row:
            xs[item] -= edge


def far_ends(
    graph: LineGraph, rows: list[list[str]], xs: dict[str, int], rot: dict[str, int]
) -> dict[str, float]:
    """The bricks whose takers all lie past the row under the bus, each with its takers' centre."""
    if len(rows) < 2 or not rows[0]:
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


def end_targets(
    graph: LineGraph, ends: dict[str, float], rot: dict[str, int], lo: int, hi: int
) -> dict[str, int]:
    """The far bricks outside ``lo`` to ``hi``: the lower half of their taker centres to the left, nearest first, the rest to the right."""
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


def clearance(graph: LineGraph, item: str, *others: str) -> int:
    """Cells kept between the item and its neighbour: ``PIPE_GAP`` when both carry pipes, one when either does."""
    piped = graph.piped(item)
    beside = [graph.piped(o) for o in others if o != item]
    if piped and any(beside):
        return PIPE_GAP
    return 1 if piped or any(beside) else 0


def partners_centre(
    graph: LineGraph, block: list[str], row: list[str], xs: dict[str, int]
) -> float | None:
    """The mean centre of the block's partners already placed along its row."""
    centres = [
        xs[other] + graph.span(other)[1] / 2
        for item in block
        for other in [
            *(p for p, *_ in graph.links[item]),
            *(m for m, *_ in graph.feeds[item]),
        ]
        if other in row and other in xs and other not in block
    ]
    return sum(centres) / len(centres) if centres else None


def centred(
    graph: LineGraph, row: list[str], targets: dict[str, int], rot: dict[str, int]
) -> dict[str, int]:
    """The targets with every run of siblings wanting one x spread about it."""
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


__all__ = [
    "CROSSING_ROW",
    "LANE",
    "LANE_MAX",
    "LANE_TRIES",
    "LOOP_GAP",
    "PIPE_GAP",
    "POCKET",
    "POCKET_SPAN",
    "Box",
    "LinesRows",
]
