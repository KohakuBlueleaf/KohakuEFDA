"""Seeded operator selection retains exploration and learns reward per work."""

import random
from collections import Counter

import pytest

from kohakulayout.solvers.local.selection import OperatorSelection


def trial(seed: int) -> tuple[list[str], dict]:
    selector = OperatorSelection(
        ("useful", "rejected", "expensive"), random.Random(seed)
    )
    selected = []
    for _ in range(2000):
        name = selector.choose()
        selected.append(name)
        selector.observe(
            name, 0.0 if name == "rejected" else 1.0, 100 if name == "expensive" else 1
        )
    return selected, selector.summary()


def test_same_seed_replays_learning_and_selection() -> None:
    assert trial(71) == trial(71)
    assert trial(71)[0] != trial(72)[0]


def test_rewards_and_work_affect_selection_without_erasing_exploration() -> None:
    selected, statistics = trial(3)
    counts = Counter(selected)
    assert counts["useful"] > 4 * counts["expensive"]
    assert counts["expensive"] > counts["rejected"] > 50
    assert sum(s["trials"] for s in statistics.values()) == len(selected)
    assert set(selected[:3]) == {"useful", "rejected", "expensive"}


def test_summary_is_a_copy_and_failures_reduce_recent_reward() -> None:
    selector = OperatorSelection(("a",), random.Random(0))
    selector.observe("a", 1.0, 0)
    before = selector.summary()
    before["a"]["trials"] = 999
    for _ in range(10):
        selector.observe("a", 0.0, 10)
    after = selector.summary()["a"]
    assert after["trials"] == 11
    assert 0 <= after["reward"] < 0.2
    assert after["work"] > 8


@pytest.mark.parametrize(
    "decay, exploration",
    [(0, 0.2), (1.1, 0.2), (0.2, -1), (0.2, 1.1), (float("nan"), 0.2)],
)
def test_invalid_probabilities_are_rejected(decay: float, exploration: float) -> None:
    with pytest.raises(ValueError):
        OperatorSelection(("a",), random.Random(0), decay, exploration)


def test_empty_operators_and_invalid_observations_are_rejected() -> None:
    with pytest.raises(ValueError):
        OperatorSelection((), random.Random(0))
    selector = OperatorSelection(("a",), random.Random(0))
    for name, reward, work in [
        ("b", 1, 1),
        ("a", -1, 1),
        ("a", float("inf"), 1),
        ("a", 1, -1),
    ]:
        with pytest.raises(ValueError):
            selector.observe(name, reward, work)
