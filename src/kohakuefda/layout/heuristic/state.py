"""The placement a search walks over, and what it costs.

The state is anchors and rotations, nothing else: no grid, no wires, no routing. That is what
makes a move cheap. A move touches one or two blocks, so only the nets on those blocks change
length, and the rest of the cost is a sweep over a few dozen rectangles.

Everything is a flat list indexed by block, so the Rust mirror can hold the same arrays.
``recompute`` rebuilds every term from scratch and is the oracle the incremental updates are
held to. Wirelength is the span between a wire's two pins: a lower bound on the routed path,
and here a lane is floor, so it stands in for what the route will cost.
"""

import logging
from dataclasses import dataclass

from kohakuefda.layout.site import Site
from kohakuefda.model.geometry import (
    ROTATIONS,
    Edge,
    rotate_cell,
    rotate_edge,
    rotated_size,
)

log = logging.getLogger(__name__)
FROZEN = ("slot", "edge")


@dataclass(frozen=True)
class Weights:
    """What each term of the cost is worth."""

    area: float = 1.0
    wire: float = 1.0
    overlap: float = 8.0
    group: float = 8.0
    shut: float = 8.0

    @classmethod
    def of(cls, params: dict) -> "Weights":
        return cls(
            area=float(params["w_area"]),
            wire=float(params["w_wire"]),
            overlap=float(params["w_overlap"]),
            group=float(params["w_group"]),
            shut=float(params["w_shut"]),
        )


@dataclass(frozen=True)
class Scale:
    """What the terms are measured against, taken from the placement the walk starts at.

    A raw cost carries the instance's size, so a schedule tuned on one scenario means nothing
    on another and the paper schedules, which assume a cost near one, do not cool at all.
    """

    area: float = 1.0
    wire: float = 1.0

    @classmethod
    def of(cls, terms: "Terms") -> "Scale":
        return cls(max(1.0, float(terms.area)), max(1.0, float(terms.wire)))


@dataclass
class Terms:
    """The cost split into what it is made of, so a report can name the trade."""

    area: int = 0
    wire: int = 0
    overlap: int = 0
    group: int = 0
    shut: int = 0

    def total(self, weights: Weights, scale: "Scale") -> float:
        return (
            weights.area * self.area / scale.area
            + weights.wire * self.wire / scale.wire
            + weights.overlap * self.overlap / scale.area
            + weights.group * self.group / scale.wire
            + weights.shut * self.shut
        )


class Placement:
    """Anchors and rotations for every block, with the cost kept current as they move."""

    def __init__(self, site: Site, weights: Weights) -> None:
        self.site = site
        self.weights = weights
        self.ids = sorted(site.blocks)
        self.index = {block_id: i for i, block_id in enumerate(self.ids)}
        self.count = len(self.ids)
        self.area_rect = site.area
        self._shape()
        self._wires()
        self._groups()
        self.x = [0] * self.count
        self.y = [0] * self.count
        self.rotation = [0] * self.count
        self.w = [self.size[b][0][0] for b in range(self.count)]
        self.h = [self.size[b][0][1] for b in range(self.count)]
        self.length = [0] * len(self.wire_from)
        self.extra = [0] * self.count
        self.terms = Terms()
        self.scale = Scale()

    # ---- what never changes ---------------------------------------------

    def _shape(self) -> None:
        """Footprint size and pin offsets for every block at every rotation, worked out once."""
        site = self.site
        self.size: list[list[tuple[int, int]]] = []
        self.offset: list[list[list[tuple[int, int]]]] = []
        self.pad: list[list[tuple[int, int, int, int]]] = []
        self.slot: list[dict] = []
        self.frozen = [False] * self.count
        self.powered = [False] * self.count
        self.margin = [0] * self.count
        for block_id in self.ids:
            block = site.blocks[block_id]
            keys = list(block.pins)
            self.slot.append({key: i for i, key in enumerate(keys)})
            wired = {
                key
                for wire in site.touching[block_id]
                for key in (wire.source, wire.sink)
                if key in block.pins
            }
            sizes = []
            offsets = []
            pads = []
            for rotation in ROTATIONS:
                sizes.append(rotated_size(block.width, block.height, rotation))
                turned = []
                edges = {Edge.W: 0, Edge.N: 0, Edge.E: 0, Edge.S: 0}
                for key in keys:
                    cell, edge = block.port_of(key)
                    turned.append(
                        rotate_cell(
                            cell[0], cell[1], block.width, block.height, rotation
                        )
                    )
                    if key in wired:
                        edges[rotate_edge(edge, rotation)] = 1
                offsets.append(turned)
                pads.append(
                    (edges[Edge.W], edges[Edge.N], edges[Edge.E], edges[Edge.S])
                )
            self.size.append(sizes)
            self.offset.append(offsets)
            self.pad.append(pads)
            self.frozen[self.index[block_id]] = block.constraint in FROZEN or bool(
                block.group
            )
            self.powered[self.index[block_id]] = block.powered
            self.margin[self.index[block_id]] = site._group_room(block)

    def _wires(self) -> None:
        """Each wire as a pair of block-and-pin, and which wires each block carries."""
        site = self.site
        self.wire_from: list[tuple[int, object]] = []
        self.wire_to: list[tuple[int, object]] = []
        self.incident: list[list[int]] = [[] for _ in range(self.count)]
        for wire in site.wires:
            source = self.index[site.owner[wire.source].id]
            sink = self.index[site.owner[wire.sink].id]
            here = len(self.wire_from)
            self.wire_from.append((source, self.slot[source][wire.source]))
            self.wire_to.append((sink, self.slot[sink][wire.sink]))
            self.incident[source].append(here)
            if sink != source:
                self.incident[sink].append(here)

    def _groups(self) -> None:
        """The blocks the game binds together, as indices."""
        self.group_of = [-1] * self.count
        self.groups: list[list[int]] = []
        for name in sorted(self.site.groups):
            members = [
                self.index[b.id] for b in self.site.groups[name] if b.id in self.index
            ]
            for member in members:
                self.group_of[member] = len(self.groups)
            self.groups.append(members)

    # ---- reading the state ----------------------------------------------

    def rect(self, block: int) -> tuple[int, int, int, int]:
        return (
            self.x[block],
            self.y[block],
            self.x[block] + self.w[block],
            self.y[block] + self.h[block],
        )

    def anchors(self) -> dict[str, tuple[int, int, int]]:
        return {
            block_id: (self.x[i], self.y[i], self.rotation[i])
            for i, block_id in enumerate(self.ids)
        }

    def adopt(self, anchors: dict[str, tuple[int, int, int]]) -> None:
        """Take a whole placement — the seed, or another search's answer."""
        for block_id, (x, y, rotation) in anchors.items():
            i = self.index[block_id]
            self.x[i], self.y[i], self.rotation[i] = x, y, rotation
            self.w[i], self.h[i] = self.size[i][rotation // 90]
        self.terms = self.recompute()

    def cost(self) -> float:
        return self.terms.total(self.weights, self.scale)

    def rescale(self) -> None:
        """Measure the terms against where the walk starts, so the cost is near one."""
        self.scale = Scale.of(self.terms)

    # ---- the cost, from scratch -----------------------------------------

    def recompute(self) -> Terms:
        """Every term rebuilt from the anchors: the oracle the incremental cost is held to."""
        terms = Terms()
        terms.area = self._area()
        for index in range(len(self.wire_from)):
            self.length[index] = self._span(index)
        terms.wire = sum(self.length)
        terms.overlap = sum(
            self._overlap(a, b)
            for a in range(self.count)
            for b in range(a + 1, self.count)
        )
        terms.group = self._faults()
        terms.shut = sum(
            self._shut_pair(a, b)
            for a in range(self.count)
            for b in range(a + 1, self.count)
        )
        return terms

    def _area(self) -> int:
        return self._bbox()

    def _span(self, wire: int) -> int:
        source, source_slot = self.wire_from[wire]
        sink, sink_slot = self.wire_to[wire]
        here = self.offset[source][self.rotation[source] // 90][source_slot]
        there = self.offset[sink][self.rotation[sink] // 90][sink_slot]
        across = (self.x[source] + here[0]) - (self.x[sink] + there[0])
        down = (self.y[source] + here[1]) - (self.y[sink] + there[1])
        return abs(across) + abs(down)

    def _overlap(self, a: int, b: int) -> int:
        ax0, ay0, ax1, ay1 = self.rect(a)
        bx0, by0, bx1, by1 = self.rect(b)
        wide = min(ax1, bx1) - max(ax0, bx0)
        high = min(ay1, by1) - max(ay0, by0)
        return wide * high if wide > 0 and high > 0 else 0

    def room(self, block: int) -> tuple[int, int, int, int]:
        """The area this block may stand in: the whole of it, less the border a Depot Bus
        part has to leave for the bricks that seat against it (DEP-06)."""
        edge = self.margin[block]
        x0, y0, x1, y1 = self.area_rect
        return (x0 + edge, y0 + edge, x1 - edge, y1 - edge)

    def _outside(self, block: int) -> int:
        """Cells of a footprint that fall outside the room it may use."""
        x0, y0, x1, y1 = self.rect(block)
        ax0, ay0, ax1, ay1 = self.room(block)
        over = max(0, ax0 - x0) + max(0, x1 - ax1)
        down = max(0, ay0 - y0) + max(0, y1 - ay1)
        return over * (y1 - y0) + down * (x1 - x0)

    def _faults(self) -> int:
        """How far the groups are from what the game demands, plus anything out of the area."""
        total = sum(self._outside(b) for b in range(self.count))
        for members in self.groups:
            total += self._group_fault(members)
        return total

    def _group_fault(self, members: list[int]) -> int:
        """A group's members must sit together; count the cells they are apart by."""
        if len(members) < 2:
            return 0
        spread = 0
        for i, first in enumerate(members):
            best = min(
                self._gap(first, second) for j, second in enumerate(members) if i != j
            )
            spread += best
        return spread

    def _gap(self, a: int, b: int) -> int:
        ax0, ay0, ax1, ay1 = self.rect(a)
        bx0, by0, bx1, by1 = self.rect(b)
        wide = max(0, max(bx0 - ax1, ax0 - bx1))
        high = max(0, max(by0 - ay1, ay0 - by1))
        return wide + high

    # ---- the cost, as a block moves -------------------------------------

    def _overlap_of(self, block: int) -> int:
        """Cells this block shares with any other, the loop written out because it is the
        hottest thing in the search: two of these run for every move proposed."""
        x, y, w, h = self.x, self.y, self.w, self.h
        ax0 = x[block]
        ay0 = y[block]
        ax1 = ax0 + w[block]
        ay1 = ay0 + h[block]
        total = 0
        for other in range(self.count):
            if other == block:
                continue
            bx0 = x[other]
            bx1 = bx0 + w[other]
            left = max(ax0, bx0)
            right = min(ax1, bx1)
            if right <= left:
                continue
            by0 = y[other]
            by1 = by0 + h[other]
            top = max(ay0, by0)
            bottom = min(ay1, by1)
            if bottom > top:
                total += (right - left) * (bottom - top)
        return total

    def _shut_pair(self, a: int, b: int) -> int:
        """Cells of one block's lane corridor that the other is standing on.

        A connection always costs a cell in front of the port (LOG-11), and a lane needs a way
        out, so a block is entitled to one free cell along each edge that carries a wired port
        and to none along the edges that carry nothing — machines may share those (PLC-01).
        Counting only the port cell lets the search pack a machine so tight that the port is
        clear and no path to it exists.
        """
        shut = 0
        for first, second in ((a, b), (b, a)):
            west, north, east, south = self.pad[first][self.rotation[first] // 90]
            room = self.extra[first]
            fx0 = self.x[first] - west - room
            fy0 = self.y[first] - north - room
            fx1 = self.x[first] + self.w[first] + east + room
            fy1 = self.y[first] + self.h[first] + south + room
            sx0 = self.x[second]
            sy0 = self.y[second]
            wide = min(fx1, sx0 + self.w[second]) - max(fx0, sx0)
            if wide <= 0:
                continue
            high = min(fy1, sy0 + self.h[second]) - max(fy0, sy0)
            if high > 0:
                shut += wide * high
        return shut - 2 * self._overlap(a, b)

    def _shut_of(self, block: int) -> int:
        return sum(
            self._shut_pair(block, other)
            for other in range(self.count)
            if other != block
        )

    def _bbox(self) -> int:
        x, y, w, h = self.x, self.y, self.w, self.h
        x0 = y0 = 1 << 30
        x1 = y1 = -(1 << 30)
        for block in range(self.count):
            left = x[block]
            top = y[block]
            x0 = min(x0, left)
            y0 = min(y0, top)
            right = left + w[block]
            bottom = top + h[block]
            x1 = max(x1, right)
            y1 = max(y1, bottom)
        return (x1 - x0) * (y1 - y0)

    def put(self, block: int, x: int, y: int, rotation: int) -> None:
        """Move one block and fold the change into the running cost.

        Only the pairs touching this block and the wires on it can have changed, so the cost
        stays exact without a sweep over everything; the bounding box is the exception, and it
        is one pass over a few dozen anchors.
        """
        terms = self.terms
        length = self.length
        incident = self.incident[block]
        before_overlap = self._overlap_of(block)
        before_shut = self._shut_of(block)
        before_fault = self._outside(block)
        group = self.group_of[block]
        members = self.groups[group] if group >= 0 else None
        if members is not None:
            before_fault += self._group_fault(members)
        was = [length[wire] for wire in incident]
        self.x[block] = x
        self.y[block] = y
        self.rotation[block] = rotation
        self.w[block], self.h[block] = self.size[block][rotation // 90]
        terms.overlap += self._overlap_of(block) - before_overlap
        terms.shut += self._shut_of(block) - before_shut
        after_fault = self._outside(block)
        if members is not None:
            after_fault += self._group_fault(members)
        terms.group += after_fault - before_fault
        for slot, wire in enumerate(incident):
            span = self._span(wire)
            terms.wire += span - was[slot]
            length[wire] = span
        terms.area = self._bbox()

    def swap(self, first: int, second: int) -> None:
        """Exchange two blocks' anchors.

        Done as two moves rather than one: a single fold would count the pair's own overlap
        twice, once from each side, while a move at a time is exact because only the pairs
        touching the block that moved can have changed.
        """
        target = (self.x[second], self.y[second])
        source = (self.x[first], self.y[first])
        self.put(first, target[0], target[1], self.rotation[first])
        self.put(second, source[0], source[1], self.rotation[second])
