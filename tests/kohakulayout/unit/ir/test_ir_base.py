"""ir/base.py: rates, attrs, ids, digests and the level registry."""

from fractions import Fraction

import pytest

from kohakulayout.errors import IRError
from kohakulayout.ir import LEVELS, Assessment, Layout, Netlist, Node, Problem
from kohakulayout.ir.base import (
    canonical_json,
    check_attrs,
    digest_of,
    parse_rate,
    rate_text,
)


def test_rates_parse_and_serialise() -> None:
    assert parse_rate("7/2") == Fraction(7, 2)
    assert parse_rate(30) == Fraction(30)
    assert parse_rate(Fraction(1, 3)) == Fraction(1, 3)
    assert rate_text(Fraction(30)) == "30/1"
    with pytest.raises(ValueError):
        parse_rate(True)


def test_ids_and_attrs_are_checked() -> None:
    with pytest.raises(ValueError):
        Node(id="1bad")
    assert check_attrs({"pack": {"k": 1}}, "x") == []
    assert check_attrs({"bad key": {}}, "x") == [
        "x: attrs key 'bad key' is not a pack namespace"
    ]
    assert check_attrs({"pack": 3}, "x") == ["x: attrs['pack'] is not a dict"]


def test_digest_ignores_dict_order() -> None:
    assert digest_of({"a": 1, "b": [1, 2]}) == digest_of({"b": [1, 2], "a": 1})
    assert (
        canonical_json({"b": 1, "a": Fraction(1, 2).__str__()}) == '{"a":"1/2","b":1}'
    )


def test_registry_holds_every_level() -> None:
    assert {"netlist", "layout", "assessment", "problem"} <= set(LEVELS)
    assert LEVELS["netlist"] is Netlist and LEVELS["layout"] is Layout
    assert LEVELS["assessment"] is Assessment and LEVELS["problem"] is Problem


def test_verify_lists_every_problem() -> None:
    assessment = Assessment(metrics={}, valid=True, complete=False)
    with pytest.raises(IRError) as info:
        assessment.verify()
    assert "placed" in str(info.value) and "valid requires" in str(info.value)
