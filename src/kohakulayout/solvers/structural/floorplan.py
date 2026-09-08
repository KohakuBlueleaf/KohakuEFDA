"""The rows representation: items packed into rows with a channel between rows; channels become reservations."""

import math
import random
from typing import Any

from kohakulayout.ir import Refusal
from kohakulayout.ir.geometry import XY, rotate_size
from kohakulayout.physics.protocol import Anchor
from kohakulayout.solvers.structural.representation import register

Structure = dict[str, Any]
MARGIN = 2


def items_of(world: Any) -> list[str]:
    """What a floorplan places: instances of macros as one item, every other free leaf on its own."""
    netlist = world.problem.netlist
    out: list[str] = []
    for cell_id, cell in netlist.cells.items():
        if cell.macro is not None or (
            cell.footprint is not None and cell.constraint.kind == "free"
        ):
            out.append(cell_id)
    return sorted(out)


def item_size(world: Any, item: str, rot: int) -> tuple[int, int]:
    netlist = world.problem.netlist
    fp = netlist.footprint_for(item)
    if fp is None:
        return (1, 1)
    return rotate_size(fp.width, fp.height, rot)


@register
class Rows:
    """Rows of items left to right from a two-cell margin, ``gap`` cells between items, a channel of ``channel`` cells above and under each row."""

    id = "rows"

    def __init__(self, channel: int = 2, gap: int = 2, rows: int = 0) -> None:
        self.channel = channel
        self.gap = gap
        self.rows = rows

    def initial(self, ctx: Any, rng: random.Random) -> Structure:
        world = ctx.world
        items = items_of(world)
        order, _ = world.problem.netlist.flow_order()
        rank = {c: i for i, c in enumerate(order)}
        items.sort(key=lambda c: (rank.get(c, 0), c))
        count = self.rows or max(1, round(math.sqrt(len(items))))
        per_row = max(1, math.ceil(len(items) / count))
        rows = [items[i : i + per_row] for i in range(0, len(items), per_row)]
        return {"rows": rows, "rot": dict.fromkeys(items, 0)}

    def geometry(
        self, structure: Structure, ctx: Any
    ) -> dict[str, tuple[int, int, int, int]]:
        """Each item's box (x, y, w, h) from its row and position, before any legalisation."""
        world = ctx.world
        out: dict[str, tuple[int, int, int, int]] = {}
        y = self.channel
        for row in structure["rows"]:
            x = MARGIN
            height = 0
            for item in row:
                w, h = item_size(world, item, structure["rot"].get(item, 0))
                out[item] = (x, y, w, h)
                x += w + self.gap
                height = max(height, h)
            y += height + self.channel
        return out

    def channels(
        self, structure: Structure, ctx: Any
    ) -> list[tuple[str, str, tuple[XY, ...], str | None]]:
        """One reservation per carrier under each row, spanning the row's width."""
        world = ctx.world
        geometry = self.geometry(structure, ctx)
        carriers = sorted({n.carrier for n in world.netlist.nets.values()})
        out = []
        if not any(structure["rows"]):
            return out
        width = max(b[0] + b[2] for b in geometry.values()) + self.gap
        bands = [(0, "top")]
        for index, row in enumerate(structure["rows"]):
            if not row:
                continue
            boxes = [geometry[item] for item in row]
            bands.append((max(b[1] + b[3] for b in boxes), str(index)))
        for y, name in bands:
            cells = tuple(
                (x, y + dy)
                for dy in range(self.channel)
                for x in range(width)
                if world.in_grid((x, y + dy))
            )
            for carrier in carriers:
                out.append(
                    (
                        f"channel:{name}:{carrier}",
                        world.carrier_layer(carrier),
                        cells,
                        carrier,
                    )
                )
        return out

    def decode(self, structure: Structure, builder: Any) -> Refusal | None:
        world = builder.world
        geometry = self.geometry(structure, world_ctx(builder))
        for row in structure["rows"]:
            for item in row:
                if item in builder.placements or item in world.instance_anchors:
                    continue
                x, y, _, _ = geometry[item]
                rot = structure["rot"].get(item, 0)
                cell = world.problem.netlist.cells[item]
                refusal = (
                    builder.place_instance(item, x, y, rot)
                    if cell.macro is not None
                    else builder.place(item, Anchor(x=x, y=y, rot=rot))
                )
                if refusal is not None:
                    return refusal
        return None

    def mutate(self, structure: Structure, rng: random.Random) -> Structure:
        rows = [list(r) for r in structure["rows"]]
        rot = dict(structure["rot"])
        items = [i for r in rows for i in r]
        if not items:
            return {"rows": rows, "rot": rot}
        move = rng.choice(("swap", "move", "flip"))
        if move == "swap" and len(items) >= 2:
            a, b = rng.sample(items, 2)
            for row in rows:
                for k, item in enumerate(row):
                    row[k] = b if item == a else a if item == b else item
        elif move == "move":
            item = rng.choice(items)
            for row in rows:
                if item in row:
                    row.remove(item)
            target = rng.randrange(len(rows) + 1)
            if target == len(rows):
                rows.append([item])
            else:
                rows[target].insert(rng.randint(0, len(rows[target])), item)
            rows = [r for r in rows if r]
        else:
            item = rng.choice(items)
            rot[item] = (rot.get(item, 0) + 90) % 180
        return {"rows": rows, "rot": rot}


class _Ctx:
    def __init__(self, world: Any) -> None:
        self.world = world


def world_ctx(builder: Any) -> Any:
    return _Ctx(builder.world)


__all__ = ["Rows", "Structure", "item_size", "items_of"]
