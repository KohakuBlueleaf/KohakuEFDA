"""Exact rate arithmetic and the ``Rate`` field."""

from fractions import Fraction

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.rates import Rate, lanes_needed, per_minute, to_fraction


class Holder(EfdaModel):
    rate: Rate


def test_per_minute_is_exact() -> None:
    assert per_minute(1, 2) == Fraction(30)
    assert per_minute(2, 3) == Fraction(40)
    assert per_minute(1, 8) == Fraction(15, 2)


def test_lanes_needed_rounds_up() -> None:
    assert lanes_needed(Fraction(30), Fraction(30)) == 1
    assert lanes_needed(Fraction(31), Fraction(30)) == 2
    assert lanes_needed(Fraction(0), Fraction(30)) == 0


def test_rate_field_accepts_int_str_float_and_serialises_as_string() -> None:
    assert Holder(rate=30).rate == Fraction(30)
    assert Holder(rate="7/2").rate == Fraction(7, 2)
    assert Holder(rate=0.5).rate == Fraction(1, 2)
    assert Holder(rate="7/2").model_dump()["rate"] == "7/2"
    assert Holder.model_validate_json('{"rate": "15/4"}').rate == Fraction(15, 4)


def test_to_fraction_keeps_fractions() -> None:
    value = Fraction(3, 7)
    assert to_fraction(value) is value
