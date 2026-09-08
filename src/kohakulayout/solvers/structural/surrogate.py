"""The surrogate: what a floorplan is worth before legalisation, from its geometry alone."""

from fractions import Fraction
from typing import Any


def half_perimeter(world: Any, boxes: dict[str, tuple[int, int, int, int]]) -> int:
    """The sum over nets of the half perimeter of the box around its items' centres."""
    netlist = world.problem.netlist
    total = 0
    for net in netlist.nets.values():
        xs: list[int] = []
        ys: list[int] = []
        for ref in net.pins():
            box = boxes.get(ref.cell)
            if box is None:
                continue
            xs.append(2 * box[0] + box[2])
            ys.append(2 * box[1] + box[3])
        if len(xs) >= 2:
            total += (max(xs) - min(xs) + max(ys) - min(ys)) // 2
    return total


def surrogate(
    representation: Any,
    structure: Any,
    ctx: Any,
    wire_weight: Fraction = Fraction(1, 4),
) -> Fraction:
    """Area of the box around every item plus a weighted wire estimate; lower is better."""
    boxes = representation.geometry(structure, ctx)
    if not boxes:
        return Fraction(0)
    width = max(x + w for x, _, w, _ in boxes.values()) - min(
        x for x, _, _, _ in boxes.values()
    )
    height = max(y + h for _, y, _, h in boxes.values()) - min(
        y for _, y, _, _ in boxes.values()
    )
    return Fraction(width * height) + wire_weight * half_perimeter(ctx.world, boxes)


__all__ = ["half_perimeter", "surrogate"]
