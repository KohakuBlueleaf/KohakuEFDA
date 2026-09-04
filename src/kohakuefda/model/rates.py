"""Exact rates: ``Fraction`` units per minute, serialised as strings."""

from fractions import Fraction
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

BELT_PER_MIN = Fraction(30)
PIPE_PER_MIN = Fraction(120)


def to_fraction(value: object) -> Fraction:
    """Coerce int, float, str or Fraction into an exact ``Fraction``."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, float):
        return Fraction(str(value))
    return Fraction(value)


Rate = Annotated[
    Fraction,
    BeforeValidator(to_fraction),
    PlainSerializer(str, return_type=str),
    WithJsonSchema({"type": "string", "pattern": r"^-?\d+(/\d+)?$"}),
]


def per_minute(count: int | Fraction, seconds: int | Fraction) -> Fraction:
    """Rate in units per minute for ``count`` units every ``seconds`` seconds."""
    return Fraction(count) * 60 / Fraction(seconds)


def lanes_needed(rate: Fraction, lane_capacity: Fraction) -> int:
    """Smallest number of lanes of ``lane_capacity`` that carries ``rate``."""
    if rate <= 0:
        return 0
    return -(-rate // lane_capacity)
