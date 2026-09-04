"""A genetic search over placements.

The chromosome is the placement itself, so crossover has to recombine positions rather than a
sequence. It cuts the board with a line and takes each parent's blocks from one side, which is
the spatial analogue of order crossover: a cluster that worked in one parent arrives in the
child whole, in the place it worked.

A child is repaired rather than discarded — the cut leaves overlaps where the two halves meet,
and pushing them apart is cheaper than throwing the recombination away. With ``ga_local_moves``
above zero each child is then annealed briefly, which is what makes the difference between a
genetic algorithm on this landscape and a slow random search.
"""

import logging
import random

from kohakuefda.layout.heuristic.anneal import Annealer
from kohakuefda.layout.heuristic.state import Placement

log = logging.getLogger(__name__)
Anchors = dict[str, tuple[int, int, int]]


class Evolver:
    """Breeds placements; ``run`` leaves the state at the best one it bred."""

    def __init__(self, state: Placement, params: dict, rng: random.Random) -> None:
        self.state = state
        self.params = params
        self.rng = rng
        self.size = max(4, int(params["ga_population"]))
        self.generations = max(1, int(params["ga_generations"]))
        self.crossover = float(params["ga_crossover"])
        self.mutation = float(params["ga_mutation"])
        self.tournament = max(2, int(params["ga_tournament"]))
        self.elite = max(0, min(int(params["ga_elitism"]), self.size - 1))
        self.local = max(0, int(params["ga_local_moves"]))
        self.every = max(1, int(params["frame_every"]))

    # ---- one individual --------------------------------------------------

    def score(self, anchors: Anchors) -> float:
        self.state.adopt(anchors)
        return self.state.cost()

    def improve(self, anchors: Anchors, moves: int) -> tuple[float, Anchors]:
        """Anneal one child briefly, so the population holds local optima and not noise."""
        if not moves:
            return self.score(anchors), anchors
        settings = {
            **self.params,
            "sa_moves": moves,
            "sa_polish": max(1, moves // 4),
            "frame_every": 1 << 30,
        }
        self.state.adopt(anchors)
        Annealer(self.state, settings, self.rng).run()
        return self.state.cost(), self.state.anchors()

    # ---- the population --------------------------------------------------

    def seed(self, first: Anchors) -> list[tuple[float, Anchors]]:
        """The first generation: the given placement, and mutations of it."""
        people = [self.improve(first, self.local)]
        while len(people) < self.size:
            people.append(self.improve(self.jolt(first), self.local))
        people.sort(key=lambda person: person[0])
        return people

    def jolt(self, anchors: Anchors) -> Anchors:
        """A placement with some of its blocks thrown elsewhere, to spread the first draw."""
        state = self.state
        out = dict(anchors)
        for index, block_id in enumerate(state.ids):
            if state.frozen[index] or self.rng.random() > self.mutation:
                continue
            x0, y0, x1, y1 = state.room(index)
            rotation = self.rng.choice((0, 90, 180, 270))
            width, height = state.size[index][rotation // 90]
            out[block_id] = (
                self.rng.randint(x0, max(x0, x1 - width)),
                self.rng.randint(y0, max(y0, y1 - height)),
                rotation,
            )
        return out

    def pick(self, people: list[tuple[float, Anchors]]) -> Anchors:
        return min(
            self.rng.sample(people, min(self.tournament, len(people))),
            key=lambda person: person[0],
        )[1]

    def cross(self, first: Anchors, second: Anchors) -> Anchors:
        """One parent's blocks on one side of a cut line, the other's on the far side."""
        state = self.state
        x0, y0, x1, y1 = state.area_rect
        vertical = self.rng.random() < 0.5
        line = self.rng.randint(x0, x1) if vertical else self.rng.randint(y0, y1)
        out: Anchors = {}
        for index, block_id in enumerate(state.ids):
            here = first[block_id]
            side = here[0] if vertical else here[1]
            out[block_id] = here if side < line else second[block_id]
        return out

    def run(self, first: Anchors, observe=None, cancelled=None) -> Anchors:
        """Breed for the whole budget and give back the best placement seen."""
        people = self.seed(first)
        for generation in range(self.generations):
            if cancelled is not None and cancelled():
                break
            children: list[tuple[float, Anchors]] = people[: self.elite]
            while len(children) < self.size:
                mother = self.pick(people)
                father = self.pick(people)
                child = (
                    self.cross(mother, father)
                    if self.rng.random() < self.crossover
                    else dict(mother)
                )
                if self.rng.random() < self.mutation:
                    child = self.jolt(child)
                children.append(self.improve(child, self.local))
            children.sort(key=lambda person: person[0])
            people = children[: self.size]
            if observe is not None and generation % self.every == 0:
                self.state.adopt(people[0][1])
                observe(self.frame(generation, people[0][0]))
        self.state.adopt(people[0][1])
        return people[0][1]

    def frame(self, generation: int, best: float) -> dict:
        return {
            "kind": "search",
            "step": generation,
            "of": self.generations,
            "best": round(best, 3),
            "cost": round(self.state.cost(), 3),
            "terms": vars(self.state.terms),
            "blocks": [
                [block_id, self.state.x[i], self.state.y[i], self.state.rotation[i]]
                for i, block_id in enumerate(self.state.ids)
            ],
        }
