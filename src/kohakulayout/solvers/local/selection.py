"""Seeded, cost-aware selection among local search operators."""

import math
import random
from dataclasses import dataclass

DECAY = 0.2
EXPLORATION = 0.2
IMPROVEMENT_REWARD = 1.0
DELTA_REWARD = 64.0
PLATEAU_REWARD = 0.02


@dataclass
class OperatorStats:
    trials: int = 0
    reward: float = 0.0
    work: float = 1.0


def reward(delta: float | None, accepted: bool) -> float:
    """An accepted improvement earns more the larger it is, an accepted plateau a little, anything else nothing."""
    if not accepted or delta is None:
        return 0.0
    if delta < 0:
        return IMPROVEMENT_REWARD + DELTA_REWARD * -delta
    return PLATEAU_REWARD


class OperatorSelection:
    """Sample operators using recent reward per square root of charged work."""

    def __init__(
        self,
        names: tuple[str, ...],
        rng: random.Random,
        decay: float = DECAY,
        exploration: float = EXPLORATION,
    ) -> None:
        if not names or not 0 < decay <= 1 or not 0 <= exploration <= 1:
            raise ValueError(
                "operators and finite decay/exploration probabilities required"
            )
        self.names = tuple(dict.fromkeys(names))
        self.rng = rng
        self.decay = decay
        self.exploration = exploration
        self.stats = {name: OperatorStats() for name in self.names}

    def choose(self) -> str:
        """Try every operator once, then mix weighted exploitation with uniform exploration."""
        unseen = [name for name, stats in self.stats.items() if not stats.trials]
        if unseen:
            return self.rng.choice(unseen)
        if self.rng.random() < self.exploration:
            return self.rng.choice(self.names)

        weights = [
            self.stats[name].reward / math.sqrt(max(1.0, self.stats[name].work))
            for name in self.names
        ]
        if not any(weights):
            return self.rng.choice(self.names)
        return self.rng.choices(self.names, weights=weights, k=1)[0]

    def observe(self, name: str, reward: float, work: int) -> None:
        """Update one operator after a completed proposal, including rejected proposals."""
        if name not in self.stats:
            raise ValueError(f"unknown operator {name!r}")
        if not math.isfinite(reward) or reward < 0 or work < 0:
            raise ValueError("reward and work must be finite and nonnegative")

        stats = self.stats[name]
        weight = self.decay if stats.trials else 1.0
        stats.reward += weight * (reward - stats.reward)
        stats.work += weight * (max(1, work) - stats.work)
        stats.trials += 1

    def summary(self) -> dict[str, dict[str, float | int]]:
        return {
            name: {"trials": stats.trials, "reward": stats.reward, "work": stats.work}
            for name, stats in self.stats.items()
        }


__all__ = [
    "DECAY",
    "EXPLORATION",
    "OperatorSelection",
    "OperatorStats",
    "reward",
]
