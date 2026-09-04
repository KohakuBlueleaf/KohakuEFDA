"""Searches over the genome, with the spread as the decoder.

Each of these spends the same currency — one decoded lattice — so they can be compared at an
equal budget instead of argued about. ``restart`` is the handcrafted baseline: draw a genome,
decode it, keep the best, and never look at what the last one was worth. ``anneal`` walks from
one genome to a neighbour and sometimes accepts a worse one. ``evolve`` keeps a population and
breeds the survivors.

A decoded genome is whole or it is worthless, so ``value`` prices a broken layout past every
whole one and the walk never has to leave the legal region to get anywhere.
"""

import logging
import math
import random
from collections.abc import Callable

from kohakuefda.layout.genome import Genome, Score, cross, mutate

log = logging.getLogger(__name__)
BROKEN = 1 << 20
Decode = Callable[[Genome], Score]
Sample = Callable[[int], Genome]


def value(score: Score) -> float:
    """A score as one number: what is missing priced past anything a whole layout costs."""
    missed, unrouted, area, wires = score
    return (missed + unrouted) * BROKEN + area + wires


def restart(
    decode: Decode, sample: Sample, rng: random.Random, budget: int, gaps: range
) -> tuple[Score, Genome]:
    """Independent draws, best kept: what the handcrafted spread already does."""
    best: tuple[Score, Genome] | None = None
    for attempt in range(budget):
        genome = sample(attempt)
        score = decode(genome)
        if best is None or score < best[0]:
            best = (score, genome)
    return best


def anneal(
    decode: Decode, sample: Sample, rng: random.Random, budget: int, gaps: range
) -> tuple[Score, Genome]:
    """A walk from one genome to a neighbour, uphill moves accepted less and less often.

    The temperature is set from the spread of the first few draws rather than a constant, so
    it means the same thing on a scenario whose layouts differ by ten cells and on one whose
    layouts differ by a thousand.
    """
    current = sample(0)
    score = decode(current)
    best = (score, current)
    warm = [value(decode(sample(i))) for i in range(1, min(8, budget))]
    spread = (max(warm) - min(warm)) if warm else 1.0
    start = max(1.0, spread)
    for step in range(len(warm) + 1, budget):
        temperature = start * (0.01 / 1.0) ** (step / max(1, budget))
        candidate = mutate(current, rng, gaps)
        got = decode(candidate)
        delta = value(got) - value(score)
        if delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9)):
            current, score = candidate, got
            if got < best[0]:
                best = (got, candidate)
    return best


def evolve(
    decode: Decode, sample: Sample, rng: random.Random, budget: int, gaps: range
) -> tuple[Score, Genome]:
    """A population bred by order crossover and local mutation, the worst replaced each round.

    Order crossover keeps a run of one parent where it is and fills the rest in the other
    parent's sequence, so a chain of the flow that worked survives whole into the child.
    """
    size = max(4, min(16, budget // 8))
    people = [(decode(g), g) for g in (sample(i) for i in range(size))]
    people.sort(key=lambda p: p[0])
    spent = size
    while spent < budget:
        first = min(rng.sample(people, min(3, len(people))), key=lambda p: p[0])[1]
        second = min(rng.sample(people, min(3, len(people))), key=lambda p: p[0])[1]
        child = cross(first, second, rng)
        if rng.random() < 0.7:
            child = mutate(child, rng, gaps)
        score = decode(child)
        spent += 1
        if score < people[-1][0]:
            people[-1] = (score, child)
            people.sort(key=lambda p: p[0])
    return people[0]


SEARCHES: dict[str, Callable[..., tuple[Score, Genome]]] = {
    "restart": restart,
    "anneal": anneal,
    "evolve": evolve,
}
MIXED = "mixed"
