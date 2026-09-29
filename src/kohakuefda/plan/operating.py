"""Exact operating points and capacity-packed transport lanes."""

from fractions import Fraction


class OperatingPointError(ValueError):
    """Activity or capacity outside the physical range."""


def operating_points(activity: Fraction, machines: int) -> tuple[Fraction, ...]:
    """Fill whole machines before a fractional remainder, preserving total activity."""
    activity = Fraction(activity)
    if machines < 0 or activity < 0 or activity > machines:
        raise OperatingPointError(
            "activity must lie between zero and the machine count"
        )
    return tuple(
        min(Fraction(1), max(Fraction(0), activity - i)) for i in range(machines)
    )


def packed_rates(rate: Fraction, capacity: Fraction) -> tuple[Fraction, ...]:
    """Split a nonnegative rate into full lanes and at most one partial lane."""
    rate, capacity = Fraction(rate), Fraction(capacity)
    if rate < 0 or capacity <= 0:
        raise OperatingPointError("rate must be nonnegative and capacity positive")
    count, remainder = divmod(rate, capacity)
    return (capacity,) * int(count) + ((remainder,) if remainder else ())


__all__ = ["OperatingPointError", "operating_points", "packed_rates"]
