"""Representations: a structure a solver mutates, and the decoder that turns it into placements through the builder."""

import random
from typing import Any, Protocol, runtime_checkable

from kohakulayout.errors import SolverError
from kohakulayout.ir import Refusal
from kohakulayout.physics.protocol import Anchor


@runtime_checkable
class Representation(Protocol):
    id: str

    def initial(self, ctx: Any, rng: random.Random) -> Any: ...
    def decode(self, structure: Any, builder: Any) -> Refusal | None: ...
    def mutate(self, structure: Any, rng: random.Random) -> Any: ...
    def channels(
        self, structure: Any, ctx: Any
    ) -> list[tuple[str, str, tuple[tuple[int, int], ...], str | None]]: ...
    def geometry(
        self, structure: Any, ctx: Any
    ) -> dict[str, tuple[int, int, int, int]]: ...


class Coordinate:
    """The identity: a structure is the anchor of every leaf; decoding places them there."""

    id = "coordinate"

    def initial(self, ctx: Any, rng: random.Random) -> dict[str, tuple[int, int, int]]:
        """Every cell at the anchor in-order placement would give it, found by placing and rolling back."""
        world = ctx.world
        token = ctx.snapshot()
        order, _ = world.netlist.flow_order()

        def walk(builder: Any) -> None:
            for cell_id in order:
                if cell_id in builder.placements:
                    continue
                anchor = builder.first_open(cell_id)
                if anchor is not None:
                    builder.place(cell_id, anchor)

        ctx.attempt(walk, label="initial")
        structure = {c: (p.x, p.y, p.rot) for c, p in world.placements.items()}
        ctx.restore(token)
        return structure

    def decode(
        self, structure: dict[str, tuple[int, int, int]], builder: Any
    ) -> Refusal | None:
        for cell_id, (x, y, rot) in structure.items():
            if cell_id in builder.placements:
                continue
            refusal = builder.place(cell_id, Anchor(x=x, y=y, rot=rot))
            if refusal is not None:
                return refusal
        return None

    def mutate(
        self, structure: dict[str, tuple[int, int, int]], rng: random.Random
    ) -> dict[str, tuple[int, int, int]]:
        if not structure:
            return dict(structure)
        out = dict(structure)
        cell_id = rng.choice(sorted(out))
        x, y, rot = out[cell_id]
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        step = rng.randint(1, 3)
        out[cell_id] = (x + dx * step, y + dy * step, rot)
        return out

    def channels(self, structure: Any, ctx: Any) -> list:
        return []

    def geometry(
        self, structure: dict[str, tuple[int, int, int]], ctx: Any
    ) -> dict[str, tuple[int, int, int, int]]:
        world = ctx.world
        out = {}
        for cell_id, (x, y, rot) in structure.items():
            fp = world.footprint_of(cell_id)
            if fp is not None:
                w, h = (
                    (fp.width, fp.height) if rot in (0, 180) else (fp.height, fp.width)
                )
                out[cell_id] = (x, y, w, h)
        return out


REPRESENTATIONS: dict[str, type] = {Coordinate.id: Coordinate}


def register(representation: type) -> type:
    REPRESENTATIONS[representation.id] = representation
    return representation


def get(name: str, **kwargs: Any) -> Any:
    cls = REPRESENTATIONS.get(name)
    if cls is None:
        raise SolverError(
            f"no representation {name!r}; known: {sorted(REPRESENTATIONS)}"
        )
    return cls(**kwargs)


__all__ = ["REPRESENTATIONS", "Coordinate", "Representation", "get", "register"]
