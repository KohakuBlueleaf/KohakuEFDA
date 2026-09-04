"""The decisions a layout is made of, as something a search can hold and change.

The handcrafted spread already makes these three choices and, left to itself, draws them at
random: the order the blocks are laid in, how wide the corridors are, and which way along the
flow the walk runs. Everything else about a layout follows from them, because the spread is
deterministic once they are fixed. So they are the genome, the spread is the decoder, and the
random restarts the baseline does are the crudest possible search over this space.

The flow order is a *good* order — laying each chain of the flow to its end gave 82 lane cells
where taking the flow a rank at a time gave 611 — so a genome starts from it and the moves
disturb it locally rather than reshuffling.
"""

import random
from dataclasses import dataclass, replace

Score = tuple[int, int, int, int]
WORST: Score = (1 << 30, 1 << 30, 1 << 30, 1 << 30)


@dataclass(frozen=True)
class Genome:
    """One layout's worth of decisions: the laying order, the corridor width, the direction."""

    order: tuple[str, ...]
    gap: int
    top_down: bool


def seeded(order: list[str], gap: int, top_down: bool) -> Genome:
    return Genome(tuple(order), gap, top_down)


def mutate(genome: Genome, rng: random.Random, gaps: range) -> Genome:
    """One local change: two blocks exchanged, a run reversed, a block carried elsewhere, the
    corridor widened or narrowed, or the walk turned around.

    The order moves are local on purpose. The flow order it starts from is worth keeping, so
    the search perturbs it rather than replacing it.
    """
    pick = rng.random()
    order = list(genome.order)
    if pick < 0.3 and len(order) > 1:
        i = rng.randrange(len(order) - 1)
        order[i], order[i + 1] = order[i + 1], order[i]
    elif pick < 0.5 and len(order) > 2:
        i = rng.randrange(len(order) - 1)
        j = min(len(order), i + 2 + rng.randrange(4))
        order[i:j] = reversed(order[i:j])
    elif pick < 0.7 and len(order) > 2:
        i = rng.randrange(len(order))
        block = order.pop(i)
        order.insert(rng.randrange(len(order) + 1), block)
    elif pick < 0.9 and len(gaps) > 1:
        return replace(genome, gap=rng.choice(list(gaps)))
    else:
        return replace(genome, top_down=not genome.top_down)
    return replace(genome, order=tuple(order))


def cross(first: Genome, second: Genome, rng: random.Random) -> Genome:
    """Order crossover: a run of the first parent kept where it is, the rest of the blocks in
    the order the second parent has them, so both parents' sequences survive in part and the
    child is still a permutation."""
    size = len(first.order)
    if size < 2:
        return first
    start = rng.randrange(size)
    stop = start + 1 + rng.randrange(size - start)
    kept = set(first.order[start:stop])
    rest = [b for b in second.order if b not in kept]
    order = rest[:start] + list(first.order[start:stop]) + rest[start:]
    return Genome(
        tuple(order),
        first.gap if rng.random() < 0.5 else second.gap,
        first.top_down if rng.random() < 0.5 else second.top_down,
    )
