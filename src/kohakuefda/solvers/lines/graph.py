"""The netlist read for the lines: the items that stand in rows, the side cells beside a
machine, who feeds whom through which pins, the loops and the groups (game-knowledge
PLC-09 to PLC-13)."""

from typing import Any

from kohakuefda.physics.boundaries import BRICK_KINDS, PART_KIND
from kohakuefda.physics.facts import lane_facts
from kohakuefda.solvers.lines.depths import SIDE_GAP, LineDepths
from kohakuefda.solvers.lines.order import LineOrder
from kohakulayout.solvers.structural.floorplan import item_size, items_of
from kohakulayout.state.attach import options_at

PIPE_SIDES = {"outlet": "W", "inlet": "E"}
SMALL_GROUP = 3
JOIN_GAP = 3
Link = tuple[str, str, str, str, str]


def partners(netlist: Any, cell_id: str, direction: str) -> list[str]:
    """The cells at the other end of the cell's nets: its consumers (``out``) or its makers (``in``)."""
    out: list[str] = []
    for net in netlist.nets.values():
        mine = net.sources if direction == "out" else net.sinks
        others = net.sinks if direction == "out" else net.sources
        if any(r.cell == cell_id for r in mine):
            out += [r.cell for r in others if r.cell != cell_id and r.cell not in out]
    return out


class LineGraph(LineDepths, LineOrder):
    """``parts``, ``bricks``, ``machines`` (every other free item), ``sides`` per
    machine by face, ``links`` toward consumers and ``feeds`` toward makers, each
    ``(partner, own pin, partner pin, carrier, net)``."""

    def __init__(self, world: Any) -> None:
        self.world = world
        self.netlist = netlist = world.problem.netlist
        cells = netlist.cells
        self.parts = sorted(c for c in cells if cells[c].kind == PART_KIND)
        self.bricks = sorted(c for c in cells if cells[c].kind in BRICK_KINDS)
        self.sides: dict[str, dict[str, list[str]]] = {}
        self.side_of: dict[str, str] = {}
        self.band_right: set[str] = set()
        self._regions: tuple[dict[str, int], list[list[str]]] | None = None

        free = items_of(world)
        self.machines: list[str] = []
        for cell_id in free:
            face = PIPE_SIDES.get(cells[cell_id].kind)
            mates = (
                partners(netlist, cell_id, "out" if face == "W" else "in")
                if face
                else []
            )
            mate = next((m for m in mates if m in free), None)
            if mate is None:
                self.machines.append(cell_id)
                continue
            self.sides.setdefault(mate, {"W": [], "E": []})[face].append(cell_id)
            self.side_of[cell_id] = mate

        self.items = [*self.bricks, *self.machines]
        self.links: dict[str, list[Link]] = {i: [] for i in self.items}
        self.feeds: dict[str, list[Link]] = {i: [] for i in self.items}
        for net in netlist.nets.values():
            pairs = [(sc, sp, tc, tp) for (sc, sp), (tc, tp), _ in lane_facts(net)] or [
                (a.cell, a.pin, b.cell, b.pin) for a in net.sources for b in net.sinks
            ]
            for source, own, sink, far in pairs:
                if source == sink or source not in self.links or sink not in self.links:
                    continue
                self.links[source].append((sink, own, far, net.carrier, net.id))
                self.feeds[sink].append((source, far, own, net.carrier, net.id))

    def sides_of(self, item: str, rot: int = 0) -> dict[str, list[str]]:
        """The item's side cells by face, the faces swapped when it is turned about."""
        sides = self.sides.get(item, {"W": [], "E": []})
        return {"W": sides["E"], "E": sides["W"]} if rot == 180 else sides

    def port_xs(self, item: str, pin_id: str, rot: int = 0) -> list[int]:
        """The columns of the pin's ports from the item's left edge, turned by ``rot``."""
        fp = self.netlist.footprint_for(item)
        pin = next((p for p in self.netlist.pins_of(item) if p.id == pin_id), None)
        if fp is None or pin is None:
            return []
        return [attach[0] for _, attach, _ in options_at(fp, pin, 0, 0, rot)]

    def port_dx(self, item: str, pin_id: str, rot: int = 0) -> int:
        xs = self.port_xs(item, pin_id, rot)
        return xs[0] if xs else 0

    def port_range(self, item: str, pin_id: str, rot: int = 0) -> tuple[int, int]:
        xs = self.port_xs(item, pin_id, rot)
        return (min(xs), max(xs)) if xs else (0, 0)

    def kind_of(self, item: str) -> tuple[Any, ...]:
        """What tells one machine type from another: its footprint and its pins."""
        fp = self.netlist.footprint_for(item)
        return (
            fp.id if fp is not None else None,
            *sorted(p.id for p in self.netlist.pins_of(item)),
        )

    def condensed(self) -> tuple[dict[str, int], list[list[str]]]:
        """The strongly connected components of the links (Tarjan) in flow order, and each item's component."""
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

    def regions(self) -> tuple[dict[str, int], list[list[str]]]:
        """The loops as single nodes: neighbouring loops merged, and every single
        neighbour of a kind the loop holds drawn in; in flow order."""
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
        self._regions = ({c: k for k, r in enumerate(regions) for c in r}, regions)
        return self._regions

    def loop_of(self, item: str) -> list[str]:
        """The items of the item's loop, itself alone outside a loop."""
        node_of, nodes = self.regions()
        return nodes[node_of[item]]

    def clusters(self) -> list[list[str]]:
        """The groups, one chain each: the components of the machines without the
        loops, the terminals and the fans (an item whose takers fall apart without it),
        each of those then joined to the neighbouring group with the most lanes, a
        bus-fed one first; the bricks with the machine they feed; bus-fed groups first,
        then by size."""
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
        groups = self.absorbed([sorted(g) for g in groups if g])
        groups.sort(
            key=lambda g: (0 if any(c in self.bricks for c in g) else 1, -len(g), g[0])
        )
        return groups

    def absorbed(self, groups: list[list[str]]) -> list[list[str]]:
        """Every bus-fed group of at most ``SMALL_GROUP`` machines joined to the largest bus-fed group."""
        fed = [g for g in groups if any(c in self.bricks for c in g)]
        if len(fed) < 2:
            return groups

        main = max(fed, key=len)
        merged = list(main)
        out: list[list[str]] = []
        for g in groups:
            if g is main:
                continue
            machines = [c for c in g if c not in self.bricks]
            if g in fed and len(machines) <= SMALL_GROUP:
                merged += g
            else:
                out.append(g)
        return [sorted(merged), *out]

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

    def fed_by_bus(self, item: str) -> bool:
        return any(m in self.bricks for m, *_ in self.feeds[item])

    def piped(self, item: str) -> bool:
        """Whether a pipe joins the item to another item."""
        return any(
            c == "pipe" for _, _, _, c, _ in [*self.links[item], *self.feeds[item]]
        )

    def siblings(self, a: str, b: str) -> bool:
        """Whether two items feed the same consumers and nothing else."""
        mine = {t for t, *_ in self.links[a]}
        return bool(mine) and mine == {t for t, *_ in self.links[b]}

    def exclusive(self, item: str, link: Link, row: set[str]) -> bool:
        """Whether the link's partner has no other partner in the item's row."""
        partner = link[0]
        others = {t for t, *_ in self.links[partner]}
        others |= {m for m, *_ in self.feeds[partner]}
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

    def stacks(
        self, item: str, rot: int = 0
    ) -> dict[str, list[list[tuple[str, int, int]]]]:
        """The item's side cells per face as columns of ``(cell, dx, dy)``: a column
        as tall as the item plus one, the next one gap further out; a face whose cells
        share a net starts ``JOIN_GAP`` off so their trunk has a straight cell."""
        _, h = item_size(self.world, item, rot)
        out: dict[str, list[list[tuple[str, int, int]]]] = {"W": [], "E": []}
        for face, cells in self.sides_of(item, rot).items():
            columns: list[list[tuple[str, int, int]]] = []
            dx = JOIN_GAP if self.shared_net(cells) else SIDE_GAP
            for cell in cells:
                _, ch = item_size(self.world, cell, 0)
                if columns and columns[-1][-1][2] + ch <= h + 1:
                    columns[-1].append((cell, dx, columns[-1][-1][2] + ch))
                    continue
                if columns:
                    dx += max(item_size(self.world, c, 0)[0] for c, _, _ in columns[-1])
                    dx += SIDE_GAP
                columns.append([(cell, dx, ch)])
            out[face] = columns
        return out

    def shared_net(self, cells: list[str]) -> bool:
        """Whether two of the cells are pins of one net."""
        return any(
            len({r.cell for r in net.pins() if r.cell in cells}) > 1
            for net in self.netlist.nets.values()
        )

    def span(self, item: str, rot: int = 0) -> tuple[int, int, int, int]:
        """The item's box with its side cells: ``(lead, width, trail, height)``."""
        w, h = item_size(self.world, item, rot)
        reach = {"W": 0, "E": 0}
        for face, columns in self.stacks(item, rot).items():
            for column in columns:
                for cell, dx, dy in column:
                    cw = item_size(self.world, cell, 0)[0]
                    reach[face] = max(reach[face], dx + cw)
                    h = max(h, dy)
        return reach["W"], w, reach["E"], h


__all__ = ["JOIN_GAP", "PIPE_SIDES", "SIDE_GAP", "LineGraph", "partners"]
