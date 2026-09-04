"""Simulated annealing over a placement.

The state is the placement itself, a move touches one or two blocks, and the cost is folded in
where it changed, so the walk runs at tens of thousands of moves a second and a neighbour
really is a neighbour. That is the whole difference from perturbing an encoding and rebuilding
the layout from it: there the cost of two "neighbours" is uncorrelated and the acceptance test
decides nothing.

The first temperature is measured, not set (``schedule.first_temperature``); the range limit
shrinks with it, so late moves are corrections; and the walk reheats when it has gone a long
way without improving.
"""

import logging
import math
import random
from dataclasses import dataclass, field, replace

from kohakuefda.layout.heuristic.moves import Moves
from kohakuefda.layout.heuristic.schedule import SCHEDULES, first_temperature
from kohakuefda.layout.heuristic.state import Placement

log = logging.getLogger(__name__)


@dataclass
class Trace:
    """What the walk did, for a watcher and for the benchmark."""

    steps: int = 0
    accepted: int = 0
    best: float = math.inf
    temperature: float = 0.0
    reheats: int = 0
    curve: list[tuple[int, float, float]] = field(default_factory=list)


class Annealer:
    """Anneals one placement in place; ``run`` leaves it at the best arrangement it saw."""

    def __init__(self, state: Placement, params: dict, rng: random.Random) -> None:
        self.state = state
        self.params = params
        self.rng = rng
        self.moves = Moves(state, params, rng)
        self.budget = max(1, int(params["sa_moves"]))
        self.schedule = SCHEDULES[str(params["sa_schedule"])](params, self.budget)
        self.warmup = max(8, int(params["sa_warmup"]))
        self.accept_initial = float(params["sa_accept_initial"])
        self.patience = max(1, int(params["sa_reheat_after"]))
        self.reheats = max(0, int(params["sa_reheat"]))
        self.every = max(1, int(params["frame_every"]))
        self.polish_moves = max(0, int(params["sa_polish"]))
        self.polish_overlap = float(params["sa_polish_overlap"])
        self.window = max(1, int(params["sa_window"]))
        self.trace = Trace()

    def calibrate(self) -> float:
        """Walk at random for a moment to see what an uphill move costs on this instance."""
        uphill: list[float] = []
        for _ in range(self.warmup):
            before = self.state.cost()
            move = self.moves.propose()
            if move is None:
                break
            delta = self.state.cost() - before
            if delta > 0:
                uphill.append(delta)
            self.moves.undo(move)
        return first_temperature(uphill, self.accept_initial)

    def run(self, observe=None, cancelled=None) -> Trace:
        """Anneal for the whole budget and finish at the best placement seen."""
        state = self.state
        trace = self.trace
        state.rescale()
        first = float(self.params["sa_start_temperature"]) or self.calibrate()
        temperature = first
        best_cost = state.cost()
        best = state.anchors()
        current = best_cost
        since = 0
        window = 0
        taken = 0
        swing = 0.0
        for step in range(self.budget):
            if cancelled is not None and cancelled():
                break
            move = self.moves.propose()
            if move is None:
                break
            after = state.cost()
            delta = after - current
            swing += delta if delta > 0 else -delta
            if delta <= 0 or self.rng.random() < math.exp(
                -delta / max(temperature, 1e-9)
            ):
                current = after
                taken += 1
                window += 1
                if after < best_cost - 1e-9:
                    best_cost, best, since = after, state.anchors(), 0
                    if observe is not None:
                        observe(self.frame(step, temperature, best_cost, "improve"))
            else:
                self.moves.undo(move)
                since += 1
            if step % self.window == 0 and step:
                temperature = self.schedule(
                    step=step,
                    first=first,
                    temperature=temperature,
                    acceptance=window / self.window,
                    delta=swing / self.window / max(abs(current), 1.0),
                )
                window = 0
                swing = 0.0
                self.moves.narrow(temperature / max(first, 1e-9))
            if step % self.every == 0 and step:
                trace.curve.append((step, current, best_cost))
                if observe is not None:
                    observe(self.frame(step, temperature, best_cost, "search"))
            if since > self.patience and trace.reheats < self.reheats:
                temperature = first * 0.5
                trace.reheats += 1
                since = 0
        state.adopt(best)
        self.polish(cancelled)
        trace.steps = self.budget
        trace.accepted = taken
        trace.best = best_cost
        trace.temperature = temperature
        return trace

    def polish(self, cancelled=None) -> None:
        """Harden the walk's answer: overlap priced far higher and only improvements taken.

        Annealing explores with overlap as a soft penalty, which is what lets it slide a
        machine through its neighbour to the other side; a layout with any overlap left does
        not exist, so the last phase prices it out and takes nothing that is not better.
        """
        state = self.state
        if not self.polish_moves:
            return
        soft = state.weights
        state.weights = replace(
            soft, overlap=self.polish_overlap, shut=self.polish_overlap
        )
        self.moves.narrow(0.0)
        current = state.cost()
        for _ in range(self.polish_moves):
            if cancelled is not None and cancelled():
                break
            move = self.moves.propose()
            if move is None:
                break
            after = state.cost()
            if after < current:
                current = after
            else:
                self.moves.undo(move)
        self.separate()
        state.weights = soft
        state.terms = state.recompute()

    def separate(self) -> None:
        """Push overlapping blocks apart until none are left.

        Random polish moves can leave a cell or two of overlap because the one move that would
        clear it is a needle in the neighbourhood. This walks the offending pairs and takes
        whichever of the four ways out removes the most overlap, whatever it does to the rest
        of the cost: a layout with any overlap does not exist, so nothing else can outweigh it.
        """
        state = self.state
        movable = self.moves.movable
        for _ in range(state.count * 8):
            if not state.terms.overlap:
                return
            pair = self._collision(movable)
            if pair is None:
                return
            if not self._push(*pair):
                return

    def _push(self, block: int, other: int) -> bool:
        """Move one block clear of another; False when no direction helps."""
        state = self.state
        ax0, ay0, ax1, ay1 = state.rect(block)
        bx0, by0, bx1, by1 = state.rect(other)
        home = (state.x[block], state.y[block])
        rotation = state.rotation[block]
        best = state.terms.overlap
        landing = None
        for dx, dy in ((bx1 - ax0, 0), (bx0 - ax1, 0), (0, by1 - ay0), (0, by0 - ay1)):
            x, y = self.moves._inside(block, home[0] + dx, home[1] + dy, rotation)
            state.put(block, x, y, rotation)
            if state.terms.overlap < best:
                best, landing = state.terms.overlap, (x, y)
            state.put(block, home[0], home[1], rotation)
        if landing is None:
            return False
        state.put(block, landing[0], landing[1], rotation)
        return True

    def _collision(self, movable: list[int]) -> tuple[int, int] | None:
        state = self.state
        for block in movable:
            for other in range(state.count):
                if other != block and state._overlap(block, other):
                    return block, other
        return None

    def frame(self, step: int, temperature: float, best: float, kind: str) -> dict:
        """A progress frame: what the walk is doing, not just where it ended."""
        return {
            "kind": kind,
            "step": step,
            "of": self.budget,
            "temperature": round(temperature, 3),
            "cost": round(self.state.cost(), 1),
            "best": round(best, 1),
            "range": self.moves.range,
            "terms": vars(self.state.terms),
            "blocks": [
                [block_id, self.state.x[i], self.state.y[i], self.state.rotation[i]]
                for i, block_id in enumerate(self.state.ids)
            ],
        }
