"""The lines groups as stacks of row rectangles packed against the bus (game-knowledge PLC-09)."""

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


def bbox(shape: list[Rect]) -> Rect:
    x0 = min(r[0] for r in shape)
    y0 = min(r[1] for r in shape)
    x1 = max(r[0] + r[2] for r in shape)
    y1 = max(r[1] + r[3] for r in shape)
    return (x0, y0, x1 - x0, y1 - y0)


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
    """A position per group: the north groups side by side on the line, the west groups
    down the west edge, each as near the corner as the rows before allow; the others,
    larger and more linked first, by a search of at most ``NODES`` nodes over the
    corners beside or under placed rows for the smallest box plus ``weight`` cells per
    lane of trunk between partners; a group the search never placed goes under all."""
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

    def box(shapes_: list[list[Rect]]) -> int:
        rects = [r for shape in shapes_ for r in shape]
        x1 = max(r[0] + r[2] for r in rects)
        y1 = max(r[1] + r[3] for r in rects)
        return (x1 - left) * (y1 - top)

    def floor(axis: int, start: int) -> int:
        return max(
            (r[axis] + r[axis + 2] for s in placed.values() for r in s), default=start
        )

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
                if clear(shifted(shape, at[0] - bx, at[1] - by)):
                    found = (at[0] - bx, at[1] - by)
                    break
            if found is None:
                found = (
                    (floor(0, left) + channel - bx, top - by)
                    if face == "N"
                    else (left - bx, floor(1, top) + channel - by)
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
        bx, by, bw, _ = bbox(shape)
        options = []
        for cx, cy in corners(bw):
            moved = shifted(shape, cx - bx, cy - by)
            if clear(moved):
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
    for g in rest:
        if g not in best["origin"]:
            bx, by, _, _ = bbox(shapes[g])
            best["origin"][g] = (left - bx, floor(1, top) + channel - by)
            placed[g] = shifted(shapes[g], *best["origin"][g])
    origin.update(best["origin"])
    return [origin[g] for g in range(len(shapes))]


__all__ = ["NODES", "WEIGHT", "apart", "bbox", "pack_groups", "shifted"]
