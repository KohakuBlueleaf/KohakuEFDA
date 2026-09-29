"""The rows of each lines group: how deep from the bus every item stands and which way it faces."""

from itertools import pairwise
from typing import Any

from kohakulayout.ir.netlist.order import flow_order

SIDE_GAP = 1
MERGE_FEEDS = 1
STAGGER_FROM = 4


class LineDepths:
    """The depth half of ``LineGraph``; mixed into it."""

    bricks: list[str]
    links: dict[str, list[tuple]]
    feeds: dict[str, list[tuple]]
    band_right: set[str]

    def depths(self) -> tuple[dict[str, int], list[list[str]], dict[str, int]]:
        """Each item's row from the bus, the groups and each item's turn."""
        groups = self.clusters()
        depth: dict[str, int] = {}
        rot: dict[str, int] = {}
        for group in groups:
            rows, turns = self.rows_for(group)
            depth.update(rows)
            rot.update(turns)
        return depth, groups, rot

    def rows_of(self, depth: dict[str, int], group: list[str]) -> list[list[str]]:
        """The group's items by row, row 0 the bricks, each row in id order."""
        rows: list[list[str]] = [
            [] for _ in range(max((depth[c] for c in group), default=0) + 1)
        ]
        for cell_id in sorted(group):
            rows[depth[cell_id]].append(cell_id)
        return rows

    def rows_for(self, group: list[str]) -> tuple[dict[str, int], dict[str, int]]:
        """The row and the turn of every item of one group, over the loops as single
        nodes: the bricks seed row 0 (else the nodes nothing feeds, else the outside-fed
        ones whose takers have no other maker); a node stands one row past the lane its
        makers emit into; the nodes a pipe joins stand as one band facing the bus in the
        row of their nearest belt taker, ``STAGGER_FROM`` or more of them over two rows;
        a terminal or a chained node joins its only maker's row turned the other way; an
        outside-fed node stands turned one row past the lane its nearest taker reads; a
        loop nothing feeds sinks past the deepest row; sparse rows merged."""
        node_of, nodes = self.regions()
        scope = sorted({node_of[c] for c in group})
        inside = set(scope)
        makers: dict[int, list[int]] = {k: [] for k in scope}
        takers: dict[int, list[int]] = {k: [] for k in scope}
        outside: set[int] = set()
        for k in scope:
            for item in nodes[k]:
                for sink, *_ in self.links[item]:
                    b = node_of[sink]
                    if b != k and b in inside and b not in takers[k]:
                        takers[k].append(b)
                        makers[b].append(k)
                for source, *_ in self.feeds[item]:
                    if node_of[source] not in inside:
                        outside.add(k)

        row: dict[int, int] = {}
        turn: dict[int, int] = {}
        tall: dict[int, int] = {}
        stagger: dict[str, int] = {}
        bricks = {k for k in scope if any(c in self.bricks for c in nodes[k])}

        def emits(k: int) -> int:
            return row[k] + tall.get(k, 1) - 1 if turn[k] == 0 else row[k] - 1

        def reads(k: int) -> int:
            return row[k] - 1 if turn[k] == 0 else row[k]

        order, _ = flow_order(scope, [(m, k) for k in makers for m in makers[k]])
        widths = {
            k: sum(sum(self.span(c)[:3]) + SIDE_GAP for c in nodes[k]) for k in scope
        }
        seeds = bricks or {k for k in scope if not makers[k] and k not in outside}
        seeds = seeds or {
            k
            for k in scope
            if not makers[k] and all(makers[t] == [k] for t in takers[k])
        }
        band_of = self.liquid_bands(scope, nodes, node_of)

        def forward(skip: set[int]) -> None:
            for k in order:
                known = [m for m in makers[k] if m in row]
                if k in row or k in skip:
                    continue
                if k in seeds:
                    row[k], turn[k] = (0, 0) if k in bricks else (1, 0)
                elif not known:
                    continue
                elif (
                    len(makers[k]) == 1
                    and known[0] not in bricks
                    and (
                        not takers[k]
                        or chained(k, known[0], makers, takers, row, widths)
                    )
                ):
                    row[k], turn[k] = row[known[0]], 180 - turn[known[0]]
                else:
                    row[k], turn[k] = max(emits(m) for m in known) + 1, 0

        forward(set(band_of))
        for band in set(band_of.values()):
            members = [k for k in scope if band_of.get(k) == band]
            lanes = [
                emits(m)
                for k in members
                for m in makers[k]
                if m in row and band_of.get(m) != band
            ]
            below = [
                row[t]
                for k in members
                for t in takers[k]
                if t in row and band_of.get(t) != band
            ]
            at = min(below) if below else max(lanes, default=0) + 1
            for k in members:
                row[k], turn[k] = at, 0
                if len(nodes[k]) >= STAGGER_FROM:
                    tall[k] = 2
                    seq = self.mirrored(nodes[k])
                    for n, cell in enumerate(seq):
                        stagger[cell] = 0 if n < len(seq) // 2 else 1

            pending = [t for k in members for t in takers[k] if band_of.get(t) != band]
            room = max(widths[k] for k in scope)
            beside = sum(widths[k] // tall.get(k, 1) for k in members)
            while pending:
                t = pending.pop()
                if t not in row or t in bricks or t in seeds:
                    continue
                if (
                    row[t] == at
                    and any(band_of.get(m) != band for m in makers[t])
                    and beside + widths[t] <= room
                ):
                    beside += widths[t]
                    continue
                del row[t]
                pending += takers[t]

        forward(set())
        for k in reversed(order):
            known = [t for t in takers[k] if t in row]
            if k in row or not known:
                continue
            only = known[0]
            if len(known) == 1 and not makers[k] and only not in bricks:
                row[k], turn[k] = row[only], 180 - turn[only]
            else:
                row[k], turn[k] = min(reads(t) for t in known) + 1, 180

        for k in scope:
            row.setdefault(k, 1)
            turn.setdefault(k, 0)
        first = min(row.values(), default=1)
        deepest = max((row[k] + tall.get(k, 1) - 1 for k in scope), default=1)
        for k in scope:
            loose = len(nodes[k]) > 1 and not makers[k] and row[k] > first
            if loose and k not in band_of:
                row[k], turn[k] = deepest + 1, 180
        merge_rows(scope, nodes, makers, row, widths, tall, set(band_of))

        rot: dict[str, int] = {}
        for k in scope:
            node = nodes[k]
            if k in band_of:
                self.mirrored(list(node))
                for c in node:
                    rot[c] = 180 - turn[k] if c in self.band_right else turn[k]
                continue

            kinds = {self.kind_of(c) for c in node}
            heads = [
                c
                for c in node
                if any(
                    node_of[t] != k and self.kind_of(t) not in kinds
                    for t, *_ in self.links[c]
                )
            ]
            heads = heads or [
                c for c in node if any(node_of[m] != k for m, *_ in self.feeds[c])
            ]
            lead = {self.kind_of(c) for c in heads or node[:1]}
            for c in node:
                rot[c] = turn[k] if self.kind_of(c) in lead else 180 - turn[k]
        return {c: row[node_of[c]] + stagger.get(c, 0) for c in group}, rot

    def liquid_bands(
        self, scope: list[int], nodes: list[list[str]], node_of: dict[str, int]
    ) -> dict[int, int]:
        """The band of every node a pipe links inside the group: the connected sets over pipe links."""
        parent: dict[int, int] = {}

        def find(k: int) -> int:
            while parent.setdefault(k, k) != k:
                k = parent[k]
            return k

        inside = set(scope)
        for k in scope:
            for item in nodes[k]:
                for sink, _, _, carrier, _ in self.links[item]:
                    b = node_of[sink]
                    if carrier == "pipe" and b in inside:
                        parent[find(k)] = find(b)
        return {k: find(k) for k in parent}

    def mirrored(self, loop: list[str]) -> list[str]:
        """A pipe band from the middle out: the member feeding outside by belt in the
        middle, its pipe makers beside it, alternating sides by pipe distance; the
        right half turned about (``band_right``) so its pipes flow back inward."""
        members = set(loop)
        depth = {
            i: 0
            for i in loop
            if any(t not in members and c != "pipe" for t, _, _, c, _ in self.links[i])
        }
        frontier = sorted(depth)
        while frontier:
            here = frontier.pop(0)
            for m, _, _, c, _ in self.feeds[here]:
                if c == "pipe" and m in members and m not in depth:
                    depth[m] = depth[here] + 1
                    frontier.append(m)

        deepest = max(depth.values(), default=0) + 1
        left: list[str] = []
        right: list[str] = []
        for item in sorted(loop, key=lambda i: (depth.get(i, deepest), i)):
            if len(left) <= len(right):
                left.insert(0, item)
            else:
                right.append(item)
        self.band_right.update(right)
        return left + right

    def clusters(self) -> list[list[str]]: ...

    def regions(self) -> tuple[dict[str, int], list[list[str]]]: ...

    def kind_of(self, item: str) -> tuple[Any, ...]: ...

    def span(self, item: str, rot: int = 0) -> tuple[int, int, int, int]: ...


def chained(
    k: int,
    maker: int,
    makers: dict[int, list[int]],
    takers: dict[int, list[int]],
    row: dict[int, int],
    widths: dict[int, int],
) -> bool:
    """Whether a node continues its only maker along the maker's row: neither has another
    partner, the row is past the bus-fed one and with the node no wider than the widest.
    """
    if len(takers[maker]) != 1 or len(makers[k]) != 1 or row[maker] <= 1:
        return False
    filled: dict[int, int] = {}
    for other, r in row.items():
        filled[r] = filled.get(r, 0) + widths[other]
    return filled[row[maker]] + widths[k] <= max(filled.values())


def merge_rows(
    scope: list[int],
    nodes: list[list[str]],
    makers: dict[int, list[int]],
    row: dict[int, int],
    widths: dict[int, int],
    tall: dict[int, int],
    bands: set[int],
) -> None:
    """A row past the bus-fed one joins the row before it when nothing there is fed from
    it, at most ``MERGE_FEEDS`` feeds cross between them, the later holds no tall node or
    loop, the earlier no loop but a pipe band's, and together they are no wider than the
    widest row; then the rows renumbered."""
    while True:
        by_row: dict[int, list[int]] = {}
        for k in scope:
            for r in range(row[k], row[k] + tall.get(k, 1)):
                by_row.setdefault(r, []).append(k)
        order = sorted(by_row)
        width_of = {
            r: sum(widths[k] // tall.get(k, 1) for k in by_row[r]) for r in order
        }
        widest = max(width_of.values())

        merged = False
        for a, b in pairwise(order):
            if a <= 1:
                continue
            if any(k in tall or len(nodes[k]) > 1 for k in by_row[b]):
                continue
            if any(
                (len(nodes[k]) > 1 or k in tall) and k not in bands for k in by_row[a]
            ):
                continue
            if any(m in by_row[b] for k in by_row[a] for m in makers[k]):
                continue
            between = sum(1 for k in by_row[b] for m in makers[k] if m in by_row[a])
            if between > MERGE_FEEDS or width_of[a] + width_of[b] > widest:
                continue
            for k in by_row[b]:
                row[k] = a
            merged = True
            break
        if not merged:
            break

    order = sorted({r for k in scope for r in range(row[k], row[k] + tall.get(k, 1))})
    rank = {r: min(r, i + min(order)) for i, r in enumerate(order)}
    for k in scope:
        row[k] = rank[row[k]]


__all__ = ["MERGE_FEEDS", "SIDE_GAP", "STAGGER_FROM", "LineDepths"]
