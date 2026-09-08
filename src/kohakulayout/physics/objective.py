"""The objective: a pack's cost terms and weights; area and count by default."""

from fractions import Fraction
from typing import Any

from kohakulayout.ir import Layout


class DefaultObjective:
    weights: dict[str, Fraction] = {"area": Fraction(1), "units": Fraction(1)}

    def terms(
        self, layout: Layout, metrics: dict[str, Any]
    ) -> dict[str, int | Fraction]:
        return {}


def energy(objective: Any, metrics: dict[str, Any]) -> Fraction:
    """The weighted sum of the metrics the objective names; what a solver may use as a default."""
    total = Fraction(0)
    for name, weight in objective.weights.items():
        value = metrics.get(name)
        if value is not None:
            total += Fraction(weight) * Fraction(value)
    return total
