"""Acceptance and cooling for hill climbing and annealing, independent of what was placed."""

import math
import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Decision:
    accepted: bool
    probability: float
    draw: float | None = None


def decide(method: str, delta: float, heat: float, rng: random.Random) -> Decision:
    """Improvements and neutral moves pass; annealing samples an uphill move with ``exp(-delta / heat)``."""
    if delta <= 0:
        return Decision(True, 1.0)
    if method == "climb" or heat == 0:
        return Decision(False, 0.0)
    probability = math.exp(-delta / heat)
    draw = rng.random()
    return Decision(draw < probability, probability, draw)


def temperature(initial: float, final: float, work: int, horizon: int) -> float:
    """Geometric cooling by work spent, clamped to the final temperature."""
    if initial == 0:
        return 0.0
    fraction = min(1.0, work / max(1, horizon))
    return initial * (final / initial) ** fraction


def layout_delta(
    before: dict[str, Any], after: dict[str, Any], board_area: int, wire_tiebreak: float
) -> float:
    """Area first, with a route-length tie-break bounded below one cell of area, per cell of board."""
    tie = wire_tiebreak * (
        after["wire_cells"] / (board_area + after["wire_cells"])
        - before["wire_cells"] / (board_area + before["wire_cells"])
    )
    return (after["area"] - before["area"] + tie) / board_area


def gaps(metrics: dict[str, Any]) -> int:
    return int(metrics.get("missing", 0)) + int(metrics.get("unrouted", 0))


__all__ = ["Decision", "decide", "gaps", "layout_delta", "temperature"]
