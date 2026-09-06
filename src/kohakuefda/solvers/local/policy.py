"""Hill-climbing and annealing acceptance, independent of physical realization."""

import hashlib
import json
import math
import random
from dataclasses import dataclass

from kohakuefda.model.solver import Snapshot


@dataclass(frozen=True)
class Decision:
    accepted: bool
    probability: float
    draw: float | None = None


def decide(
    method: str, delta: float, temperature: float, rng: random.Random
) -> Decision:
    """Accept improvements and neutral moves; SA may accept positive energy deltas."""
    if delta <= 0:
        return Decision(True, 1.0)
    if method == "hc" or temperature == 0:
        return Decision(False, 0.0)
    probability = math.exp(-delta / temperature)
    draw = rng.random()
    return Decision(draw < probability, probability, draw)


def temperature(initial: float, final: float, work: int, horizon: int) -> float:
    """Geometric cooling by charged work, clamped to the final temperature."""
    fraction = min(1.0, work / horizon)
    if initial == 0:
        return 0.0
    return initial * (final / initial) ** fraction


def identity(snapshot: Snapshot) -> str:
    """Hash physical realization independently of anchor insertion order."""
    raw = json.loads(snapshot.payload)
    layout = json.loads(snapshot.layout_json)
    state = {
        "anchors": sorted(raw["anchors"]),
        "wires": raw["wires"],
        "ports": raw["ports"],
        "support": sorted(
            (m["id"], m["x"], m["y"], m["rotation"]) for m in layout["machines"]
        ),
    }
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def layout_delta(
    before: dict[str, float],
    after: dict[str, float],
    board_area: int,
    wire_tiebreak: float,
) -> float:
    """Difference in area-first energy with a bounded sub-cell route-length tie-break."""
    return (
        after["area"]
        - before["area"]
        + wire_tiebreak
        * (
            after["wire_path_cells"] / (board_area + after["wire_path_cells"])
            - before["wire_path_cells"] / (board_area + before["wire_path_cells"])
        )
    ) / board_area


def missing(snapshot: Snapshot) -> int:
    return sum(issue.rule == "layout.unplaced" for issue in snapshot.assessment.issues)
