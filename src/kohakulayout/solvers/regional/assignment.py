"""Minimum-cost matching of layout pins to distinct facility attachment points."""

import numpy as np

MAX_PORTS = 8


def distinct_cost(
    costs: list[dict[str, np.ndarray]], count: int, max_ports: int = MAX_PORTS
) -> np.ndarray:
    """Score each candidate's injective pin assignment, bounded by physical domain size."""
    ports = {port for pin in costs for port in pin}
    if not costs:
        return np.zeros(count)
    if any(not pin for pin in costs) or len(ports) < len(costs):
        return np.full(count, np.inf)
    if len(ports) > max_ports:
        return sum(
            (np.minimum.reduce(list(pin.values())) for pin in costs), np.zeros(count)
        )
    states = {frozenset(): np.zeros(count)}
    for pin in sorted(costs, key=len):
        following: dict[frozenset[str], np.ndarray] = {}
        for used, base in states.items():
            for port, price in pin.items():
                if port in used:
                    continue
                key = used.union((port,))
                candidate = base + price
                if key in following:
                    np.minimum(following[key], candidate, out=following[key])
                else:
                    following[key] = candidate
        states = following
        if not states:
            return np.full(count, np.inf)
    return np.minimum.reduce(list(states.values()))


__all__ = ["MAX_PORTS", "distinct_cost"]
