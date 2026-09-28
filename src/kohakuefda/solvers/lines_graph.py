"""The netlist read for the lines: which cells stand in rows, which stand beside a machine,
who feeds whom through which ports, how deep from the bus each row lies and which cells
form a group of their own.

The reference layouts (game-knowledge PLC-09 to PLC-13) are rows by stage from the bus:
the Depot Unloaders on the bus, the machines the depot feeds, then each next stage; a
chain no unloader feeds hangs beyond the row it feeds, its exit nearest to it; a chain
that feeds nothing on the bus side is a group of its own. Conduit Outlets and inlets
stand beside the machine they serve, on the face of its pipe ports.
"""

from itertools import pairwise
from typing import Any

from kohakuefda.physics.boundaries import BRICK_KINDS, PART_KIND
from kohakuefda.physics.facts import lane_facts
from kohakuefda.solvers.rows_geometry import item_of, partners, pin_id_of
from kohakulayout.ir.netlist.order import flow_order
from kohakulayout.solvers.structural.floorplan import item_size, items_of
from kohakulayout.state.attach import options_at

PIPE_SIDES = {"outlet": "W", "inlet": "E"}
ENDS = True
INTERLEAVE = False
CHAIN_ROWS = True
JOIN_CHAINS = False
SMALL_GROUP = 3
MERGE_FEEDS = 1
STAGGER_FROM = 4
MERGE_ROWS = True
MERGE_LOOPS = False
MERGE_AREA = False
LANE_GUESS = 2
BESIDE_BAND = True
ABSORB_LINKED = False
BETWEEN_TAKERS = False
OUTSIDE_FACING = False
FACING_BUS_ROW = False
Link = tuple[str, str, str, str, str]


class LineGraph:
    """The cells of a world sorted for the lines: ``parts``, ``bricks``, ``machines`` (every
    other free item that stands in a row, stashes included), ``sides`` per machine by
    face, ``links`` per item toward its consumers and ``feeds`` toward its makers, each
    ``(partner, own pin, partner pin, carrier, net)`` from the lane facts."""

    def __init__(self, world: Any) -> None:
        self.world = world
        netlist = world.problem.netlist
        self.netlist = netlist
        cells = netlist.cells
        self.kinds = {c: cells[c].kind for c in cells}
        self.parts = sorted(c for c in cells if cells[c].kind == PART_KIND)
        self.bricks = sorted(c for c in cells if cells[c].kind in BRICK_KINDS)
        free = items_of(world)
        self.sides: dict[str, dict[str, list[str]]] = {}
        self.host: dict[str, str] = {}
        self.band_right: set[str] = set()
        self.side_of: dict[str, str] = {}
        machines: list[str] = []
        for cell_id in free:
            face = PIPE_SIDES.get(self.kinds[cell_id])
            if face is None:
                machines.append(cell_id)
                continue
            mates = partners(netlist, cell_id, "out" if face == "W" else "in")
            mate = next((item_of(m) for m in mates if item_of(m) in free), None)
            if mate is None:
                machines.append(cell_id)
                continue
            self.sides.setdefault(mate, {"W": [], "E": []})[face].append(cell_id)
            self.host[cell_id] = mate
            self.side_of[cell_id] = mate
        self.machines = machines
        self.items = [*self.bricks, *machines]
        self._regions: tuple[dict[str, int], list[list[str]]] | None = None
        self.links: dict[str, list[Link]] = {i: [] for i in self.items}
        self.feeds: dict[str, list[Link]] = {i: [] for i in self.items}
        for net in netlist.nets.values():
            pairs = [(sc, sp, tc, tp) for (sc, sp), (tc, tp), _ in lane_facts(net)] or [
                (a.cell, a.pin, b.cell, b.pin) for a in net.sources for b in net.sinks
            ]
            for sc, sp, tc, tp in pairs:
                source, sink = item_of(sc), item_of(tc)
                if source == sink or source not in self.links or sink not in self.links:
                    continue
                own, far = pin_id_of(sc, sp), pin_id_of(tc, tp)
                self.links[source].append((sink, own, far, net.carrier, net.id))
                self.feeds[sink].append((source, far, own, net.carrier, net.id))

    def sides_of(self, item: str, rot: int = 0) -> dict[str, list[str]]:
        """The item's side cells by the face they stand on, the faces swapped when it is turned about."""
        sides = self.sides.get(item, {"W": [], "E": []})
        return {"W": sides["E"], "E": sides["W"]} if rot == 180 else sides

    def port_dx(self, item: str, pin_id: str, rot: int = 0) -> int:
        """The column of the pin's first port, from the item's left edge, turned by ``rot``."""
        netlist = self.netlist
        fp = netlist.footprint_for(item)
        pin = next((p for p in netlist.pins_of(item) if p.id == pin_id), None)
        if fp is None or pin is None:
            return 0
        choices = options_at(fp, pin, 0, 0, rot)
        return choices[0][1][0] if choices else 0

    def port_range(self, item: str, pin_id: str, rot: int = 0) -> tuple[int, int]:
        """The columns of the pin's ports, first to last, from the item's left edge."""
        netlist = self.netlist
        fp = netlist.footprint_for(item)
        pin = next((p for p in netlist.pins_of(item) if p.id == pin_id), None)
        if fp is None or pin is None:
            return (0, 0)
        xs = [attach[0] for _, attach, _ in options_at(fp, pin, 0, 0, rot)]
        return (min(xs), max(xs)) if xs else (0, 0)

    def edges(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for source, links in self.links.items():
            for sink, _, _, _, _ in links:
                if (source, sink) not in seen:
                    seen.add((source, sink))
                    out.append((source, sink))
        return out

    def condensed(self) -> tuple[dict[str, int], list[list[str]]]:
        """The strongly connected components of the links (Tarjan), each a loop or a
        single item, in flow order; and each item's component."""
        takers = {i: sorted({t for t, *_ in self.links[i]}) for i in self.items}
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        open_now: set[str] = set()
        stack: list[str] = []
        comps: list[list[str]] = []
        for root in self.items:
            if root in index:
                continue
            work = [(root, 0)]
            index[root] = low[root] = len(index)
            stack.append(root)
            open_now.add(root)
            while work:
                node, i = work[-1]
                if i < len(takers[node]):
                    work[-1] = (node, i + 1)
                    sink = takers[node][i]
                    if sink not in index:
                        index[sink] = low[sink] = len(index)
                        stack.append(sink)
                        open_now.add(sink)
                        work.append((sink, 0))
                    elif sink in open_now:
                        low[node] = min(low[node], index[sink])
                    continue
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    comp: list[str] = []
                    while True:
                        member = stack.pop()
                        open_now.discard(member)
                        comp.append(member)
                        if member == node:
                            break
                    comps.append(sorted(comp))
        comps.reverse()
        return {m: k for k, c in enumerate(comps) for m in c}, comps

    def kind_of(self, item: str) -> tuple[Any, ...]:
        """What tells one machine type from another: its footprint and its pins."""
        fp = self.netlist.footprint_for(item)
        return (
            fp.id if fp is not None else None,
            *sorted(p.id for p in self.netlist.pins_of(item)),
        )

    def regions(self) -> tuple[dict[str, int], list[list[str]]]:
        """The loops as single nodes: the strongly connected components, neighbouring
        loops merged into one region and every neighbour of a region of a kind the
        region holds drawn in; in flow order, and each item's region."""
        if self._regions is not None:
            return self._regions
        comp_of, comps = self.condensed()
        parent = list(range(len(comps)))

        def find(k: int) -> int:
            while parent[k] != k:
                k = parent[k]
            return k

        for item, links in self.links.items():
            for sink, *_ in links:
                a, b = comp_of[item], comp_of[sink]
                if a != b and len(comps[a]) > 1 and len(comps[b]) > 1:
                    parent[find(b)] = find(a)
        grown = True
        while grown:
            grown = False
            for k, comp in enumerate(comps):
                if find(k) != k or len(comp) > 1:
                    continue
                kind = self.kind_of(comp[0])
                beside = {find(comp_of[m]) for m, *_ in self.feeds[comp[0]]}
                beside |= {find(comp_of[t]) for t, *_ in self.links[comp[0]]}
                for region in beside:
                    if region == k or len(comps[region]) < 2:
                        continue
                    if any(self.kind_of(c) == kind for c in comps[region]):
                        parent[k] = region
                        comps[region] = [*comps[region], *comp]
                        grown = True
                        break
        merged: dict[int, set[str]] = {}
        for k, comp in enumerate(comps):
            merged.setdefault(find(k), set()).update(comp)
        regions = [sorted(m) for _, m in sorted(merged.items())]
        self._regions = (
            {c: k for k, region in enumerate(regions) for c in region},
            regions,
        )
        return self._regions

    def loop_of(self, item: str) -> list[str]:
        """The items of the loop the item belongs to, itself alone outside a loop."""
        node_of, nodes = self.regions()
        return nodes[node_of[item]]

    def clusters(self) -> list[list[str]]:
        """The groups, one chain each: the components of the machines with the loops,
        the terminals and every item whose takers fall apart without it taken out, each
        of those then joining the neighbouring component with the most lanes between
        them, a component the bus feeds first, one touching nothing a group of its own;
        the bricks with the machine they feed. The bus groups first, then by size."""
        node_of, nodes = self.regions()
        loops = {k for k, node in enumerate(nodes) if len(node) > 1}
        fed = {t for b in self.bricks for t, *_ in self.links[b]}
        stripped = {
            c for c in self.machines if not self.links[c] or node_of[c] in loops
        }
        core = [c for c in self.machines if c not in stripped]
        while True:
            fans = []
            for c in core:
                takers = {t for t, *_ in self.links[c] if t in core}
                if len(takers) < 2:
                    continue
                rest = self.parts_of([o for o in core if o != c])
                if len({g for g, comp in enumerate(rest) if takers & set(comp)}) > 1:
                    fans.append(c)
            if not fans:
                break
            stripped.update(fans)
            core = [c for c in core if c not in stripped]
        groups = [list(comp) for comp in self.parts_of(core)]
        group_of = {c: g for g, comp in enumerate(groups) for c in comp}
        pending: list[list[str]] = []
        seen: set[str] = set()
        for c in self.machines:
            if c in stripped and c not in seen:
                unit = nodes[node_of[c]] if node_of[c] in loops else [c]
                seen.update(unit)
                pending.append(list(unit))
        while pending:
            rest: list[list[str]] = []
            for unit in pending:
                counts: dict[int, int] = {}
                for c in unit:
                    for t, *_ in [*self.links[c], *self.feeds[c]]:
                        g = group_of.get(t)
                        if g is not None and t not in unit:
                            counts[g] = counts.get(g, 0) + 1
                if not counts:
                    rest.append(unit)
                    continue
                best = max(
                    counts,
                    key=lambda g: (any(c in fed for c in groups[g]), counts[g], -g),
                )
                groups[best] += unit
                group_of.update({c: best for c in unit})
            if len(rest) == len(pending):
                for unit in rest:
                    group_of.update({c: len(groups) for c in unit})
                    groups.append(list(unit))
                break
            pending = rest
        for brick in self.bricks:
            taker = next((t for t, *_ in self.links[brick] if t in group_of), None)
            if taker is not None:
                groups[group_of[taker]].append(brick)
        groups = [sorted(g) for g in groups if g]
        if JOIN_CHAINS:
            groups = self.joined(groups)
        groups = self.absorbed(groups)
        groups.sort(
            key=lambda g: (0 if any(c in self.bricks for c in g) else 1, -len(g), g[0])
        )
        return groups

    def absorbed(self, groups: list[list[str]]) -> list[list[str]]:
        """Every bus-fed group of at most ``SMALL_GROUP`` machines joined to the largest bus-fed group (under ``ABSORB_LINKED`` only one a link joins to it): a chain too small for a line of its own stands in the line's rows, its bricks on the line's bus row."""
        fed = [g for g in groups if any(c in self.bricks for c in g)]
        if len(fed) < 2:
            return groups
        main = max(fed, key=len)
        inside = set(main)
        merged = list(main)
        out: list[list[str]] = []
        for g in groups:
            if g is main:
                continue
            machines = [c for c in g if c not in self.bricks]
            linked = any(
                p in inside for c in g for p, *_ in [*self.links[c], *self.feeds[c]]
            )
            if (
                g in fed
                and len(machines) <= SMALL_GROUP
                and (linked or not ABSORB_LINKED)
            ):
                merged += g
            else:
                out.append(g)
        return [sorted(merged), *out]

    def joined(self, groups: list[list[str]]) -> list[list[str]]:
        """Groups the bus does not feed that a link joins, as one group: a chain and the chain it feeds laid as one line of mirrored halves."""
        group_of = {c: g for g, group in enumerate(groups) for c in group}
        fed = [any(c in self.bricks for c in group) for group in groups]
        parent = list(range(len(groups)))

        def find(g: int) -> int:
            while parent[g] != g:
                g = parent[g]
            return g

        for item, links in self.links.items():
            for sink, *_ in links:
                a, b = group_of.get(item), group_of.get(sink)
                if a is None or b is None or a == b or fed[a] or fed[b]:
                    continue
                parent[find(a)] = find(b)
        merged: dict[int, list[str]] = {}
        for g, group in enumerate(groups):
            merged.setdefault(find(g), []).extend(group)
        return [sorted(g) for g in merged.values()]

    def parts_of(self, cells: list[str]) -> list[list[str]]:
        """The cells grouped by the links among them, in first-seen order."""
        parent = {c: c for c in cells}

        def find(c: str) -> str:
            while parent[c] != c:
                c = parent[c]
            return c

        for c in cells:
            for other, *_ in [*self.links[c], *self.feeds[c]]:
                if other in parent:
                    parent[find(other)] = find(c)
        out: dict[str, list[str]] = {}
        for c in cells:
            out.setdefault(find(c), []).append(c)
        return list(out.values())

    def depths(self) -> tuple[dict[str, int], list[list[str]], dict[str, int]]:
        """Each item's row from the bus, the groups (``clusters``) and the turned items;
        the rows of each group on its own (``rows_for``)."""
        groups = self.clusters()
        depth: dict[str, int] = {}
        rot: dict[str, int] = {}
        for group in groups:
            rows, turns = self.rows_for(group)
            depth.update(rows)
            rot.update(turns)
        return depth, groups, rot

    def rows_for(self, group: list[str]) -> tuple[dict[str, int], dict[str, int]]:
        """The row and the turn of every item of one group, over the loops as single
        nodes: the bricks seed row 0, else the nodes nothing feeds seed row 1, else the
        outside-fed nodes whose takers have no other maker; a machine stands one row
        past the lane its makers emit into (turned about, an item emits into the lane
        above its row, facing the bus into the one below); the nodes a pipe joins stand
        as one band facing the bus in the row of their nearest belt taker, which moves
        one row on unless (``BESIDE_BAND``) it stood there fed from outside the band and
        fits beside it, ``STAGGER_FROM`` or more of them as two rows, the left half over
        the right half turned about (``liquid_bands``, ``mirrored``); a terminal joins
        its only maker's row turned the other way, so does a chained item (``chained``),
        and one nothing feeds joins its only taker's; an outside-fed item is turned about
        one row past the lane its nearest taker reads (``OUTSIDE_FACING``: facing, in
        the row over it); a belt loop nothing feeds that did not seed the group is turned
        about past the deepest row; sparse rows joined (``merge_rows``)."""
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
        bricks = {k for k in scope if comps_have(nodes[k], self.bricks)}

        tall: dict[int, int] = {}
        stagger: dict[str, int] = {}

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
                        or self.chained(k, known[0], makers, takers, row, widths)
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
                    half = len(seq) // 2
                    for n, cell in enumerate(seq):
                        stagger[cell] = 0 if n < half else 1
            pending = [t for k in members for t in takers[k] if band_of.get(t) != band]
            room = max(widths[k] for k in scope)
            beside = sum(widths[k] // tall.get(k, 1) for k in members)
            while pending:
                t = pending.pop()
                if t not in row or t in bricks or t in seeds:
                    continue
                if (
                    BESIDE_BAND
                    and row[t] == at
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
            lane = min(reads(t) for t in known)
            if len(known) == 1 and not makers[k] and only not in bricks:
                row[k], turn[k] = row[only], 180 - turn[only]
            elif (
                OUTSIDE_FACING
                and not any(m in row for m in makers[k])
                and lane >= 1
                and (lane > 1 or not bricks or FACING_BUS_ROW)
            ):
                row[k], turn[k] = lane, 0
            else:
                row[k], turn[k] = lane + 1, 180
        for k in scope:
            row.setdefault(k, 1)
            turn.setdefault(k, 0)
        first = min(row.values(), default=1)
        deepest = max((row[k] + tall.get(k, 1) - 1 for k in scope), default=1)
        for k in scope:
            if k in band_of:
                continue
            if len(nodes[k]) > 1 and not makers[k] and row[k] > first:
                row[k], turn[k] = deepest + 1, 180
        if MERGE_ROWS:
            heights = {k: max(self.span(c)[3] for c in nodes[k]) for k in scope}
            self.merge_rows(
                scope, nodes, makers, row, turn, widths, tall, set(band_of), heights
            )
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
            heads = heads or node[:1]
            lead = {self.kind_of(c) for c in heads}
            for c in node:
                rot[c] = turn[k] if self.kind_of(c) in lead else 180 - turn[k]
        return {c: row[node_of[c]] + stagger.get(c, 0) for c in group}, rot

    @staticmethod
    def chained(
        k: int,
        maker: int,
        makers: dict[int, list[int]],
        takers: dict[int, list[int]],
        row: dict[int, int],
        widths: dict[int, int],
    ) -> bool:
        """Whether a node continues its maker along the maker's row (only when
        ``CHAIN_ROWS``): the maker feeds nothing else, the node takes nothing else,
        the maker's row is not the one the bus feeds and holds, with the node, no
        more than the widest row so far."""
        if not CHAIN_ROWS:
            return False
        if len(takers[maker]) != 1 or len(makers[k]) != 1 or row[maker] <= 1:
            return False
        filled: dict[int, int] = {}
        for other, r in row.items():
            filled[r] = filled.get(r, 0) + widths[other]
        return filled[row[maker]] + widths[k] <= max(filled.values())

    def fed_by_bus(self, item: str) -> bool:
        return any(m in self.bricks for m, *_ in self.feeds[item])

    def piped(self, item: str) -> bool:
        """Whether a pipe joins the item to another item."""
        return any(c == "pipe" for _, _, _, c, _ in self.links[item]) or any(
            c == "pipe" for _, _, _, c, _ in self.feeds[item]
        )

    def liquid_bands(
        self, scope: list[int], nodes: list[list[str]], node_of: dict[str, int]
    ) -> dict[int, int]:
        """The band of every node with a pipe link inside the group: the connected sets over pipe links, one band id each; a node without one has none."""
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

    @staticmethod
    def merge_rows(
        scope: list[int],
        nodes: list[list[str]],
        makers: dict[int, list[int]],
        row: dict[int, int],
        turn: dict[int, int],
        widths: dict[int, int],
        tall: dict[int, int] | None = None,
        bands: set[int] | None = None,
        heights: dict[int, int] | None = None,
    ) -> None:
        """A row past the bus-fed one joins the row before it, each item keeping its
        turn (a feed between the two goes round the row's end, ``MERGE_FEEDS`` of them
        at most), when nothing in the earlier row is fed from it, the later holds no
        tall node (nor a loop unless ``MERGE_LOOPS``) and the earlier no belt loop (a
        pipe band's row takes it, the band counting the width of that row alone), and
        together they are no wider than the widest row or, under ``MERGE_AREA``, past
        it when the rows and a lane of ``LANE_GUESS`` cells saved outweigh the columns
        added; renumbered."""
        tall = tall or {}
        bands = bands or set()
        heights = heights or {}
        while True:
            by_row: dict[int, list[int]] = {}
            for k in scope:
                for r in range(row[k], row[k] + tall.get(k, 1)):
                    by_row.setdefault(r, []).append(k)
            order = sorted(by_row)
            width_of = {
                r: sum(widths[k] // tall.get(k, 1) for k in by_row[r]) for r in order
            }
            height_of = {
                r: max((heights.get(k, 1) for k in by_row[r]), default=1) for r in order
            }
            widest = max(width_of.values())
            total = sum(height_of.values()) + LANE_GUESS * len(order)
            merged = False
            for a, b in pairwise(order):
                if a <= 1:
                    continue
                if any(
                    k in tall or (len(nodes[k]) > 1 and not MERGE_LOOPS)
                    for k in by_row[b]
                ):
                    continue
                if any(
                    (len(nodes[k]) > 1 or k in tall) and k not in bands
                    for k in by_row[a]
                ):
                    continue
                if any(m in by_row[b] for k in by_row[a] for m in makers[k]):
                    continue
                between = sum(1 for k in by_row[b] for m in makers[k] if m in by_row[a])
                if between > MERGE_FEEDS:
                    continue
                joined = width_of[a] + width_of[b]
                saved = (height_of[b] + LANE_GUESS) * max(widest, joined)
                if joined > widest and (
                    not MERGE_AREA or (joined - widest) * total >= saved
                ):
                    continue
                for k in by_row[b]:
                    row[k] = a
                merged = True
                break
            if not merged:
                break
        order = sorted(
            {r for k in scope for r in range(row[k], row[k] + tall.get(k, 1))}
        )
        rank = {r: min(r, i + min(order)) for i, r in enumerate(order)}
        for k in scope:
            row[k] = rank[row[k]]

    def rows_of(self, depth: dict[str, int], group: list[str]) -> list[list[str]]:
        """The group's items by row, row 0 the bricks, each row in id order."""
        deepest = max((depth[c] for c in group), default=0)
        rows: list[list[str]] = [[] for _ in range(deepest + 1)]
        for cell_id in sorted(group):
            rows[depth[cell_id]].append(cell_id)
        return rows

    def exclusive(self, item: str, link: Link, row: set[str]) -> bool:
        """Whether the partner at the other end of the link has no other partner in the item's row."""
        partner = link[0]
        others = {t for t, *_ in self.links[partner]} | {
            m for m, *_ in self.feeds[partner]
        }
        return not ((others & row) - {item})

    def aligned(
        self, item: str, link: Link, xs: dict[str, int], rot: dict[str, int]
    ) -> int:
        """The x that puts the port of the item's lane in line with its partner's port."""
        partner, own, far, _, _ = link
        return (
            xs[partner]
            + self.port_dx(partner, far, rot.get(partner, 0))
            - self.port_dx(item, own, rot.get(item, 0))
        )

    def reorder(
        self,
        rows: list[list[str]],
        boxes: dict[str, tuple[int, int, int, int]],
        rot: dict[str, int],
    ) -> bool:
        """Each row sorted by the x that lines its items up with their partners' ports in
        the rows on one side, from the deepest row up (partners deeper) and then from
        the bus down (partners shallower), an item with partners along its own row only
        at their mean, just past a maker and just before a taker; a loop's members
        together at their mean, a pipe band from the middle out (``mirrored``), a
        belt loop in id order or each between the members it exchanges the most
        with when ``INTERLEAVE`` (``interleaved``); a turned item alone among items facing the bus at the
        row's end nearest its partners when ``ENDS`` (``ends``); the items the bricks feed by belt, not a pipe band's,
        feed kept together in the
        middle of their row, so the bricks stand in one run. Whether any row changed."""
        changed = False
        row_of = {i: k for k, row in enumerate(rows) for i in row}
        xs = {i: box[0] for i, box in boxes.items()}

        def centre(item: str) -> float:
            x, _, w, _ = boxes[item]
            return x + w / 2

        def sweep(sequence: list[int], deeper: bool) -> None:
            nonlocal changed
            for k in sequence:
                row = rows[k]
                pos = {i: n for n, i in enumerate(row)}
                keys: dict[str, tuple[float, int]] = {}
                for item in row:
                    found = [
                        link
                        for link in [*self.links[item], *self.feeds[item]]
                        if link[0] in row_of
                        and link[0] in xs
                        and link[0] not in row
                        and (row_of[link[0]] > k) == deeper
                    ]
                    own = [
                        link for link in found if self.exclusive(item, link, set(row))
                    ]
                    mates = [
                        (link, self.aligned(item, link, xs, rot))
                        for link in own or found
                    ]
                    fed = {m for m, *_ in self.feeds[item] if m in row}
                    feeding = {t for t, *_ in self.links[item] if t in row}
                    beside = {m for m in fed | feeding if m in boxes}
                    if mates:
                        wants = sorted(x for _, x in mates)
                        key = float(wants[(len(wants) - 1) // 2])
                    elif beside:
                        key = sum(centre(m) for m in beside) / len(beside)
                        key += 0.5 * (len(fed - feeding) - len(feeding - fed))
                    else:
                        key = float(xs.get(item, 0))
                    keys[item] = (key, pos[item])
                own_keys = dict(keys)
                for item in row:
                    loop = [i for i in self.loop_of(item) if i in row]
                    if len(loop) > 1:
                        mean = sum(own_keys[i][0] for i in loop) / len(loop)
                        if self.piped(item):
                            inner = self.mirrored(loop)
                        elif INTERLEAVE:
                            inner = self.interleaved(loop)
                        else:
                            inner = sorted(loop)
                        keys[item] = (mean, inner.index(item), 0)
                    else:
                        keys[item] = (keys[item][0], *keys[item])
                if ENDS:
                    self.ends(row, keys, rot)
                ordered = sorted(row, key=keys.get)
                fed = [
                    i
                    for i in ordered
                    if any(m in self.bricks for m, *_ in self.feeds[i])
                    and not self.piped(i)
                ]
                if fed:
                    lo, hi = ordered.index(fed[0]), ordered.index(fed[-1])
                    if any(i not in fed for i in ordered[lo:hi]):
                        loose = [(n, i) for n, i in enumerate(ordered) if i not in fed]
                        before = [i for n, i in loose if n - lo <= hi - n]
                        after = [i for n, i in loose if n - lo > hi - n]
                        ordered = [*before, *fed, *after]
                if ordered != row:
                    changed = True
                    row[:] = ordered

        sweep(list(range(len(rows) - 1, -1, -1)), True)
        sweep(list(range(len(rows))), False)
        return changed

    def mirrored(self, loop: list[str]) -> list[str]:
        """A pipe band's members from the middle out: the member that feeds outside by belt in the middle, its pipe makers beside it, theirs beyond, alternating sides by their distance over pipes, the bus-fed farthest out; the right half is turned about (``band_right``) so its pipes flow back toward the middle."""
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

    def interleaved(self, loop: list[str]) -> list[str]:
        """The loop's members in the order that puts each guest right after the host
        it exchanges the most with: the hosts are the members of the loop's most
        numerous kind in id order, the guests the rest in id order, each inserted
        after its strongest host, after the guests already there."""
        kinds: dict[tuple[Any, ...], list[str]] = {}
        for member in sorted(loop):
            kinds.setdefault(self.kind_of(member), []).append(member)
        hosts = max(kinds.values(), key=lambda members: (len(members), members[0]))
        order = list(hosts)
        for guest in sorted(loop):
            if guest in hosts:
                continue
            weight: dict[str, int] = {}
            for other, *_ in [*self.links[guest], *self.feeds[guest]]:
                if other in hosts:
                    weight[other] = weight.get(other, 0) + 1
            host = max(hosts, key=lambda h: (weight.get(h, 0), -hosts.index(h)))
            at = order.index(host) + 1
            while at < len(order) and order[at] not in hosts:
                at += 1
            order.insert(at, guest)
        return order

    def ends(
        self, row: list[str], keys: dict[str, tuple[float, ...]], rot: dict[str, int]
    ) -> None:
        """A turned item alone among items facing the bus moved to the row's end nearest
        its partners, a loop it belongs with right beside it; the keys changed in place.
        """
        guests = self.guests(row, rot)
        hosts = [i for i in row if i not in guests and rot.get(i, 0) == 0]
        if not guests:
            return
        middle = sum(keys[i][0] for i in hosts) / len(hosts)
        for i in guests:
            far = -1e9 if keys[i][0] <= middle else 1e9
            keys[i] = (far, *keys[i][1:])
            mates = {t for t, *_ in self.links[i]} | {m for m, *_ in self.feeds[i]}
            for j in row:
                if j in mates and len(self.loop_of(j)) > 1:
                    near = far + (1 if far < 0 else -1)
                    for member in self.loop_of(j):
                        if member in row:
                            keys[member] = (near, *keys[member][1:])

    def guests(self, row: list[str], rot: dict[str, int]) -> list[str]:
        """The row's turned items outside any loop, but for one whose takers all stand in the row (``BETWEEN_TAKERS``: it stands between them), when the items facing the bus are more than half the row; none otherwise."""
        guests = [
            i
            for i in row
            if rot.get(i, 0) == 180
            and len(self.loop_of(i)) == 1
            and not (
                BETWEEN_TAKERS
                and self.links[i]
                and all(t in row for t, *_ in self.links[i])
            )
        ]
        hosts = [i for i in row if i not in guests and rot.get(i, 0) == 0]
        return guests if guests and len(hosts) > len(row) / 2 else []

    def stacks(
        self, item: str, rot: int = 0
    ) -> dict[str, list[list[tuple[str, int, int]]]]:
        """The item's side cells per face as columns of ``(cell, dx, dy)`` from the
        face's corner: each column holds as many as the item's height allows plus one,
        the next column one gap further out; a face whose cells share a net stands
        ``JOIN_GAP`` off so the pipe trunk between them has a straight cell for the
        junctions the other cells join at."""
        _, h = item_size(self.world, item, rot)
        out: dict[str, list[list[tuple[str, int, int]]]] = {"W": [], "E": []}
        for face, cells in self.sides_of(item, rot).items():
            columns: list[list[tuple[str, int, int]]] = []
            dx = JOIN_GAP if self.shared_net(cells) else SIDE_GAP
            for cell in cells:
                _, ch = item_size(self.world, cell, 0)
                if columns and columns[-1][-1][2] + ch <= h + 1:
                    last = columns[-1][-1]
                    columns[-1].append((cell, dx, last[2] + ch))
                    continue
                if columns:
                    dx += max(item_size(self.world, c, 0)[0] for c, _, _ in columns[-1])
                    dx += SIDE_GAP
                columns.append([(cell, dx, ch)])
            out[face] = columns
        return out

    def shared_net(self, cells: list[str]) -> bool:
        """Whether two of the cells are pins of one net."""
        seen: set[str] = set()
        for net in self.netlist.nets.values():
            mine = {r.cell for r in net.pins() if r.cell in cells}
            if len(mine) > 1:
                return True
            seen |= mine
        return False

    def span(self, item: str, rot: int = 0) -> tuple[int, int, int, int]:
        """The item's box with its side cells: ``(lead, width, trail, height)``."""
        w, h = item_size(self.world, item, rot)
        stacks = self.stacks(item, rot)
        reach = {"W": 0, "E": 0}
        for face, columns in stacks.items():
            for column in columns:
                for cell, dx, dy in column:
                    reach[face] = max(
                        reach[face], dx + item_size(self.world, cell, 0)[0]
                    )
                    h = max(h, dy)
        return reach["W"], w, reach["E"], h

    def siblings(self, a: str, b: str) -> bool:
        """Whether two items feed the same consumers and nothing else, so they may stand edge to edge."""
        mine = {t for t, *_ in self.links[a]}
        theirs = {t for t, *_ in self.links[b]}
        return bool(mine) and mine == theirs


SIDE_GAP = 1
JOIN_GAP = 3


def comps_have(comp: list[str], cells: list[str]) -> bool:
    return any(c in cells for c in comp)


__all__ = ["JOIN_GAP", "PIPE_SIDES", "SIDE_GAP", "LineGraph"]
