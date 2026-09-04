"""Power coverage and gas zones as geometry: the greedy pylon cover and zone containment.

A pylon at ``(x, y)`` powers the square its footprint extended by its reach (game-knowledge
COV-01); a machine counts as powered when its footprint *touches* one such square — partial
coverage powers it, and a single shared cell is enough (COV-02).
``cover`` picks pylon anchors greedily: the free anchor whose square touches the most still
uncovered machines, ties to the anchor nearest ``prefer``, until nothing is left to cover or
no free anchor covers anything. A Gas Dispersing Unit's zone is the 13×13 square centred on
its 3×3 footprint (ENV-01); an environment recipe runs only with its footprint inside one
zone (ENV-02) and zones must not overlap.
"""

import numpy as np

from kohakuefda.model.layout import Cell, Rect
from kohakuefda.model.power import Pylon
from kohakuefda.model.sinks import ZONE_SIDE

PYLON_SIZE = 2


def inside(inner: Rect, outer: Rect) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


def overlaps(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def coverage_rect(pylon: Pylon, anchor: Cell) -> Rect:
    return pylon.coverage(anchor[0], anchor[1], PYLON_SIZE, PYLON_SIZE)


def zone_rect(anchor: Cell, size: int = 3) -> Rect:
    """The zone of a Gas Dispersing Unit anchored at ``anchor`` with a ``size`` footprint."""
    half = ZONE_SIDE // 2
    cx, cy = anchor[0] + size // 2, anchor[1] + size // 2
    return (cx - half, cy - half, cx + half + 1, cy + half + 1)


class Cover:
    """The pylons chosen and the machines no free anchor could cover."""

    def __init__(self, pylons: list[Cell], uncovered: list[Rect]) -> None:
        self.pylons = pylons
        self.uncovered = uncovered


def _valid_anchors(blocked: np.ndarray) -> np.ndarray:
    """Anchors whose 2×2 footprint is free, as a (height − 1) × (width − 1) mask."""
    free = ~blocked
    return free[:-1, :-1] & free[:-1, 1:] & free[1:, :-1] & free[1:, 1:]


def _anchor_range(
    pylon: Pylon, rect: Rect, width: int, height: int
) -> tuple[int, int, int, int] | None:
    """Anchors whose square touches ``rect``, as an inclusive ``(px0, py0, px1, py1)``."""
    x0, y0, x1, y1 = rect
    px0 = max(0, x0 - PYLON_SIZE - pylon.reach + 1)
    px1 = min(width - PYLON_SIZE, x1 + pylon.reach - 1)
    py0 = max(0, y0 - PYLON_SIZE - pylon.reach + 1)
    py1 = min(height - PYLON_SIZE, y1 + pylon.reach - 1)
    if px0 > px1 or py0 > py1:
        return None
    return px0, py0, px1, py1


def cover(
    pylon: Pylon, targets: list[Rect], blocked: np.ndarray, prefer: Cell
) -> Cover:
    """Greedy set cover of ``targets`` by pylon squares over the free anchors of ``blocked``."""
    height, width = blocked.shape
    if height < PYLON_SIZE or width < PYLON_SIZE:
        return Cover([], list(targets))
    valid = _valid_anchors(blocked)
    ys, xs = np.mgrid[0 : height - 1, 0 : width - 1]
    distance = np.abs(xs - prefer[0]) + np.abs(ys - prefer[1])
    far = np.iinfo(np.int64).max
    counts = np.zeros((height - 1, width - 1), dtype=np.int32)
    ranges = {}
    for index, rect in enumerate(targets):
        span = _anchor_range(pylon, rect, width, height)
        ranges[index] = span
        if span is not None:
            counts[span[1] : span[3] + 1, span[0] : span[2] + 1] += 1
    pylons: list[Cell] = []
    remaining = set(range(len(targets)))
    while remaining:
        scored = np.where(valid, counts, 0)
        best = int(scored.max())
        if best == 0:
            break
        candidates = np.where(scored == best, distance, far)
        py, px = divmod(int(np.argmin(candidates)), width - 1)
        anchor = (int(px), int(py))
        pylons.append(anchor)
        square = coverage_rect(pylon, anchor)
        for index in list(remaining):
            if overlaps(targets[index], square):
                remaining.discard(index)
                span = ranges[index]
                if span is not None:
                    counts[span[1] : span[3] + 1, span[0] : span[2] + 1] -= 1
        valid[max(0, py - 1) : py + PYLON_SIZE, max(0, px - 1) : px + PYLON_SIZE] = (
            False
        )
    return Cover(pylons, [targets[i] for i in sorted(remaining)])


def covered(pylon: Pylon, pylons: list[Cell], rect: Rect) -> bool:
    return any(overlaps(rect, coverage_rect(pylon, anchor)) for anchor in pylons)
