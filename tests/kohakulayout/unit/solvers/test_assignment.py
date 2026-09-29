"""Distinct-port scores match exhaustive assignments on small physical domains."""

import itertools

import numpy as np

from kohakulayout.solvers.regional.assignment import distinct_cost


def test_batched_assignment_matches_exhaustive_search() -> None:
    rng = np.random.default_rng(301)
    for pins in range(1, 5):
        ports = [str(i) for i in range(pins + 1)]
        costs = [
            {port: rng.integers(0, 30, size=9).astype(float) for port in ports}
            for _ in range(pins)
        ]
        expected = np.full(9, np.inf)
        for assignment in itertools.permutations(ports, pins):
            score = sum(costs[i][port] for i, port in enumerate(assignment))
            np.minimum(expected, score, out=expected)
        np.testing.assert_array_equal(distinct_cost(costs, 9), expected)


def test_hall_conflict_is_not_hidden_by_independent_nearest_ports() -> None:
    costs = [
        {"a": np.zeros(3)},
        {"a": np.ones(3)},
        {"b": np.zeros(3), "c": np.zeros(3)},
    ]
    assert np.isinf(distinct_cost(costs, 3)).all()
    np.testing.assert_array_equal(distinct_cost([], 3), np.zeros(3))


def test_large_domains_produce_a_bounded_lower_estimate() -> None:
    costs = [
        {str(i): np.array([float(i), float(9 - i)]) for i in range(10)}
        for _ in range(3)
    ]
    bound = distinct_cost(costs, 2)
    assert (bound == 0).all()
