"""Level 1 of the lines: the groups as stacks of row rectangles packed against the bus line.

The finished bases (game-knowledge PLC-09) tile the area with rectangular groups packed
edge to edge; the groups the depot feeds stand on the unloader line. ``pack_groups``
lays the bus groups side by side on the line and every other group at the corner of
the placed groups' rows that grows the box least, the trunks to its partners counted
in; a group is its rows' rectangles, so a short row leaves room beside it.
"""

from typing import Any

Rect = tuple[int, int, int, int]
WEIGHT = 1
NODES = 20000


def shifted(shape: list[Rect], x: int, y: int) -> list[Rect]:
    return [(x + rx, y + ry, rw, rh) for rx, ry, rw, rh in shape]


def apart(a: Rect, b: Rect, channel: int) -> bool:
    """Whether two rectangles leave ``channel`` cells between them on some side."""
    return (
        a[0] >= b[0] + b[2] + channel
        or b[0] >= a[0] + a[2] + channel
        or a[1] >= b[1] + b[3] + channel
        or b[1] >= a[1] + a[3] + channel
    )


def pack_groups(
    shapes: list[list[Rect]],
    faces: list[str | None],
    links: dict[tuple[int, int], int],
    left: int,
    right: int,
    top: int,
    bottom: int,
    channel: int,
    weight: int = WEIGHT,
) -> list[tuple[int, int]]:
    """A position per group. The north groups side by side on the line from ``left``
    in their order, each as far left as the rows before it allow; then the west groups
    down the west edge from the top, each as high as the rows before it allow; the
    others, the larger first and the most linked first among equals, placed by a
    search over the candidate corners (under or beside a placed row, ``channel``
    cells off it, flush with its left or its right edge), within ``NODES`` nodes,
    for the smallest box of everything placed plus ``weight`` cells per lane of trunk
    between partners, centre to centre; a group the search never placed goes under
    everything."""
    placed: dict[int, list[Rect]] = {}
    origin: dict[int, tuple[int, int]] = {}

    def clear(shape: list[Rect]) -> bool:
        for rect in shape:
            if (
                rect[0] < left
                or rect[0] + rect[2] > right
                or rect[1] < top
                or rect[1] + rect[3] > bottom
            ):
                return False
            for other in placed.values():
                if not all(apart(rect, o, channel) for o in other):
                    return False
        return True

    def bbox(shape: list[Rect]) -> Rect:
        x0 = min(r[0] for r in shape)
        y0 = min(r[1] for r in shape)
        x1 = max(r[0] + r[2] for r in shape)
        y1 = max(r[1] + r[3] for r in shape)
        return (x0, y0, x1 - x0, y1 - y0)

    def box(shapes_: list[list[Rect]]) -> int:
        rects = [r for shape in shapes_ for r in shape]
        x1 = max(r[0] + r[2] for r in rects)
        y1 = max(r[1] + r[3] for r in rects)
        return (x1 - left) * (y1 - top)

    def lanes_to(g: int) -> dict[int, int]:
        out: dict[int, int] = {}
        for (a, b), n in links.items():
            other = b if a == g else a if b == g else None
            if other is not None and other in placed:
                out[other] = out.get(other, 0) + n
        return out

    def corners(width: int = 0) -> list[tuple[int, int]]:
        out = {(left, top)}
        for shape in placed.values():
            for rx, ry, rw, rh in [*shape, bbox(shape)]:
                out.add((rx + rw + channel, ry))
                out.add((rx, ry + rh + channel))
                out.add((rx + rw - width, ry + rh + channel))
                out.add((left, ry + rh + channel))
        return sorted(out)

    for face in ("N", "W"):
        for g, shape in enumerate(shapes):
            if faces[g] != face:
                continue
            bx, by, _, _ = bbox(shape)
            found = None
            for cx, cy in corners():
                at = (cx, top) if face == "N" else (left, cy)
                moved = shifted(shape, at[0] - bx, at[1] - by)
                if clear(moved):
                    found = (at[0] - bx, at[1] - by)
                    break
            if found is None:
                x = max(
                    (r[0] + r[2] for s_ in placed.values() for r in s_), default=left
                )
                y = max(
                    (r[1] + r[3] for s_ in placed.values() for r in s_), default=top
                )
                found = (
                    (x + channel - bx, top - by)
                    if face == "N"
                    else (left - bx, y + channel - by)
                )
            origin[g] = found
            placed[g] = shifted(shape, *found)
    rest = [g for g in range(len(shapes)) if g not in placed]
    rest.sort(
        key=lambda g: (
            -bbox(shapes[g])[2] * bbox(shapes[g])[3],
            -sum(n for (a, b), n in links.items() if g in (a, b)),
            g,
        )
    )
    best: dict[str, Any] = {"cost": None, "origin": {}}
    budget = [NODES]

    def cost() -> int:
        if not placed:
            return 0
        trunks = 0
        for (a, b), n in links.items():
            if a in placed and b in placed:
                ax, ay, aw, ah = bbox(placed[a])
                bx, by, bw, bh = bbox(placed[b])
                trunks += n * (
                    abs((ax + aw // 2) - (bx + bw // 2))
                    + abs((ay + ah // 2) - (by + bh // 2))
                )
        return box(list(placed.values())) + weight * trunks

    def search(index: int) -> None:
        if budget[0] <= 0:
            return
        budget[0] -= 1
        if index == len(rest):
            here = cost()
            if best["cost"] is None or here < best["cost"]:
                best["cost"] = here
                best["origin"] = dict(origin)
            return
        g = rest[index]
        shape = shapes[g]
        bx, by, _, _ = bbox(shape)
        options = []
        for cx, cy in corners(bbox(shape)[2]):
            moved = shifted(shape, cx - bx, cy - by)
            if not clear(moved):
                continue
            options.append((box([*placed.values(), moved]), cy, cx, moved))
        options.sort(key=lambda o: o[:3])
        for grown, cy, cx, moved in options:
            if best["cost"] is not None and grown >= best["cost"]:
                break
            placed[g] = moved
            origin[g] = (cx - bx, cy - by)
            search(index + 1)
            del placed[g]
            del origin[g]

    search(0)
    if len(best["origin"]) < len(rest) + len(origin):
        for g in rest:
            if g in best["origin"]:
                continue
            shape = shapes[g]
            bx, by, _, _ = bbox(shape)
            floor = max(
                (r[1] + r[3] for s_ in placed.values() for r in s_), default=top
            )
            best["origin"][g] = (left - bx, floor + channel - by)
            placed[g] = shifted(shape, *best["origin"][g])
    origin.update(best["origin"])
    return [origin[g] for g in range(len(shapes))]


__all__ = ["NODES", "WEIGHT", "apart", "pack_groups", "shifted"]
