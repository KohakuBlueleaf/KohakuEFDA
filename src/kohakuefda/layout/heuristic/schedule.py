"""How the temperature falls.

Three schedules, because they behave differently and which one suits an instance is a question
for the benchmark, not for taste. ``geometric`` is the textbook ratio. ``fast-sa`` is the
three-stage schedule of Chen and Chang (ISPD 2005): a first stage hot enough to be a random
search, a second so cold it is nearly greedy, then a third that climbs back to hill-climb its
way out of the minimum it found. ``adaptive`` steers the temperature by the acceptance rate the
way VPR's placer does, holding it near a target.

None of them sets the first temperature: that comes from the average uphill cost actually
measured on the instance, so a scenario whose layouts differ by ten cells and one whose layouts
differ by a thousand start in the same place relative to their own landscape.
"""

import math

STAGES = 2


class Geometric:
    """``T`` falls by a fixed ratio from the first temperature to a fraction of it.

    The end is a fraction rather than a number because the first temperature is measured from
    the instance: an absolute floor would cool a big scenario to nothing and a small one hardly
    at all.
    """

    def __init__(self, params: dict, moves: int) -> None:
        self.end = max(1e-9, float(params["sa_end_temperature"]))
        self.moves = max(1, moves)

    def __call__(self, step: int, first: float, temperature: float, **_) -> float:
        return first * self.end ** (step / self.moves)


class FastSA:
    """The three-stage schedule: random, then nearly greedy, then hill-climbing.

    delta is the average cost swing over the last window as a fraction of the current
    cost, as the paper has it: a raw difference carries the instance's scale and the
    temperature then never falls.
    """

    def __init__(self, params: dict, moves: int) -> None:
        self.c = max(1.0, float(params["sa_fast_c"]))
        self.k = max(2, int(params["sa_fast_k"]))
        self.moves = max(1, moves)
        self.rounds = max(1, int(params["sa_window"]))

    def __call__(
        self, step: int, first: float, temperature: float, delta: float = 1.0, **_
    ) -> float:
        n = max(1, step // self.rounds)
        average = max(abs(delta), 1e-9)
        if n <= STAGES:
            return first
        if n <= self.k:
            return first * average / (n * self.c)
        return first * average / n


class Adaptive:
    """``T`` steered by how much is being accepted, toward a target rate."""

    def __init__(self, params: dict, moves: int) -> None:
        self.target = min(0.95, max(0.01, float(params["sa_target_accept"])))

    def __call__(
        self, step: int, first: float, temperature: float, acceptance: float = 0.5, **_
    ) -> float:
        if acceptance > self.target * 2:
            return temperature * 0.5
        if acceptance > self.target * 1.2:
            return temperature * 0.9
        if acceptance > self.target * 0.6:
            return temperature * 0.95
        return temperature * 0.8


SCHEDULES = {"geometric": Geometric, "fast-sa": FastSA, "adaptive": Adaptive}


def first_temperature(uphill: list[float], accept: float) -> float:
    """The temperature at which the average uphill move is accepted with probability
    ``accept``: the instance's own scale rather than a constant."""
    if not uphill:
        return 1.0
    average = sum(uphill) / len(uphill)
    chance = min(0.999, max(1e-6, accept))
    return max(1e-6, average / -math.log(chance))
