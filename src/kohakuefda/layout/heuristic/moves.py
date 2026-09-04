"""What a search may do to a placement, and how to take it back.

Four moves, the set VPR's placer uses plus a macro one: carry a block a little way, exchange
two, turn one where it stands, and slide everything past a line. A block is carried no further
than the range limit, which shrinks as the temperature falls, so late in a run the walk is
making small corrections rather than throwing machines across the board.

Undo is another move: putting a block back where it was folds the cost the same way taking it
away did, so a rejected proposal costs the same as an accepted one and no state is copied.
"""

import random
from dataclasses import dataclass

from kohakuefda.layout.heuristic.state import Placement

KINDS = ("displace", "swap", "rotate", "shift")
TURNS = (0, 90, 180, 270)


@dataclass(frozen=True)
class Move:
    """Which blocks a proposal touched and where they stood before it."""

    kind: str
    blocks: tuple[int, ...]
    before: tuple[tuple[int, int, int], ...]


class Moves:
    """Proposes moves on a placement and takes them back."""

    def __init__(self, state: Placement, params: dict, rng: random.Random) -> None:
        self.state = state
        self.rng = rng
        self.weights = [float(params[f"move_{kind}"]) for kind in KINDS]
        x0, y0, x1, y1 = state.area_rect
        self.span = max(x1 - x0, y1 - y0)
        self.range = max(1, int(self.span * float(params["sa_range_start"])))
        self.floor = max(1, int(params["sa_range_floor"]))
        self.movable = [b for b in range(state.count) if not state.frozen[b]]

    def narrow(self, fraction: float) -> None:
        """Shrink the range limit toward its floor as the walk cools."""
        self.range = max(self.floor, int(self.span * fraction))

    # ---- proposing -------------------------------------------------------

    def propose(self) -> Move | None:
        """One move, or ``None`` when there is nothing this search may move."""
        if not self.movable:
            return None
        kind = self.rng.choices(KINDS, self.weights)[0]
        if kind == "swap" and len(self.movable) < 2:
            kind = "displace"
        return getattr(self, f"_{kind}")()

    def _record(self, blocks: tuple[int, ...], kind: str) -> Move:
        state = self.state
        return Move(
            kind,
            blocks,
            tuple((state.x[b], state.y[b], state.rotation[b]) for b in blocks),
        )

    def _displace(self) -> Move:
        state = self.state
        block = self.rng.choice(self.movable)
        move = self._record((block,), "displace")
        reach = self.range
        x, y = self._inside(
            block,
            state.x[block] + self.rng.randint(-reach, reach),
            state.y[block] + self.rng.randint(-reach, reach),
            state.rotation[block],
        )
        state.put(block, x, y, state.rotation[block])
        return move

    def _inside(self, block: int, x: int, y: int, rotation: int) -> tuple[int, int]:
        """An anchor kept where the whole footprint stands in the area. Unbounded moves let a
        block walk off to where the bounding box no longer fits a machine word."""
        width, height = self.state.size[block][rotation // 90]
        x0, y0, x1, y1 = self.state.room(block)
        return (
            min(max(x, x0), max(x0, x1 - width)),
            min(max(y, y0), max(y0, y1 - height)),
        )

    def _swap(self) -> Move:
        first, second = self.rng.sample(self.movable, 2)
        move = self._record((first, second), "swap")
        self.state.swap(first, second)
        return move

    def _rotate(self) -> Move:
        state = self.state
        block = self.rng.choice(self.movable)
        move = self._record((block,), "rotate")
        turned = self.rng.choice([t for t in TURNS if t != state.rotation[block]])
        x, y = self._inside(block, state.x[block], state.y[block], turned)
        state.put(block, x, y, turned)
        return move

    def _shift(self) -> Move:
        """Everything past a line slid one cell, the move that opens or closes a corridor."""
        state = self.state
        axis = self.rng.random() < 0.5
        coordinate = state.y if axis else state.x
        line = coordinate[self.rng.choice(self.movable)]
        step = self.rng.choice((-1, 1))
        blocks = tuple(b for b in self.movable if coordinate[b] >= line)
        move = self._record(blocks, "shift")
        for block in blocks:
            x, y = self._inside(
                block,
                state.x[block] + (0 if axis else step),
                state.y[block] + (step if axis else 0),
                state.rotation[block],
            )
            state.put(block, x, y, state.rotation[block])
        return move

    # ---- taking it back --------------------------------------------------

    def undo(self, move: Move) -> None:
        for block, (x, y, rotation) in zip(
            reversed(move.blocks), reversed(move.before)
        ):
            self.state.put(block, x, y, rotation)
