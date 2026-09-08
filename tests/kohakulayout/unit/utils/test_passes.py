"""Passes: lanes, replicate (repairing the gates fan-out rule), surplus, balance, macros."""

from fractions import Fraction

import pytest

from kohakulayout.engine import Context
from kohakulayout.errors import IRError
from kohakulayout.ir import Carrier, Footprint, Netlist, Port
from kohakulayout.templates.physics.gates import LIBRARY, from_expressions, problem
from kohakulayout.templates.physics.gates.library import FANOUT_LIMIT
from kohakulayout.utils import (
    balance,
    bank,
    cell,
    fanout,
    lanes,
    macros,
    replicate,
    surplus,
)
from kohakulayout.utils.passes import CAPACITY, STARVED, SURPLUS, UNFED, lane_nets


def wide(sinks: int) -> Netlist:
    cells = {
        "i": cell("i", "IN"),
        **{f"o{k}": cell(f"o{k}", "OUT") for k in range(sinks)},
    }
    nl = Netlist(pack="gates", library=dict(LIBRARY), cells=cells)
    return fanout(nl, "i", [f"o{k}" for k in range(sinks)], "wire", 12)


def test_lanes_split_by_capacity() -> None:
    nl = wide(6)
    fabric = problem(nl).fabric.model_copy(
        update={
            "carriers": {
                "wire": Carrier(id="wire", layer="ground", capacity=Fraction(5))
            }
        }
    )
    assert lanes(nl, fabric).nets.keys() == nl.nets.keys()
    src = Footprint(
        id="SRC",
        width=3,
        height=3,
        ports=tuple(
            Port(id=f"y{k}", side="E", offset=k, direction="out", carrier="wire")
            for k in range(3)
        ),
    )
    cells = {"s": cell("s", "SRC"), **{f"o{k}": cell(f"o{k}", "OUT") for k in range(6)}}
    many = Netlist(pack="gates", library={**LIBRARY, "SRC": src}, cells=cells)
    many = fanout(many, "s", [f"o{k}" for k in range(6)], "wire", 12)
    packed = lanes(many, fabric)
    assert sorted(packed.nets) == ["n1/1", "n1/2", "n1/3"]
    assert [len(n.sinks) for n in packed.nets.values()] == [2, 2, 2]
    assert [str(n.sources[0]) for n in packed.nets.values()] == ["s.y0", "s.y1", "s.y2"]
    assert (
        all(n.rate == Fraction(4) for n in packed.nets.values())
        and packed.check() == []
    )
    assert lane_nets(many, many.nets["n1"], Fraction(12)) == [many.nets["n1"]]
    single = wide(1)
    assert lane_nets(single, single.nets["n1"], Fraction(5)) == [single.nets["n1"]]


def test_replicate_repairs_the_fanout_rule() -> None:
    nl = wide(FANOUT_LIMIT + 3)
    ctx = Context(problem(nl, width=32, height=16), router=None)
    findings = ctx.assess().findings
    assert any(f.rule == "gates.fanout" for f in findings)
    fixed = replicate(nl, FANOUT_LIMIT, LIBRARY["BUF"])
    assert fixed.check() == [] and len(fixed.nets["n1"].sinks) == 2
    assert {c.footprint for c in fixed.cells.values() if c.id.startswith("n1_b")} == {
        "BUF"
    }
    ctx = Context(problem(fixed, width=32, height=16), router=None)
    assert not any(f.rule == "gates.fanout" for f in ctx.assess().findings)
    deep = replicate(wide(20), 3, LIBRARY["BUF"])
    assert all(len(n.sinks) <= 3 for n in deep.nets.values()) and deep.check() == []
    with pytest.raises(ValueError, match="positive"):
        replicate(nl, 0, LIBRARY["BUF"])


def test_surplus_and_balance() -> None:
    nl = wide(2)
    extra = surplus(nl, LIBRARY["OUT"], "STASH", {"n1": 8})
    assert "n1_surplus" in extra.cells and len(extra.nets["n1"].sinks) == 3
    assert extra.cells["n1_surplus"].kind == "STASH" and extra.check() == []
    assert surplus(nl, LIBRARY["OUT"], None, {"n1": 12}).cells.keys() == nl.cells.keys()
    findings = balance(nl, {"o0": 4, "o1": 4})
    assert [f.rule for f in findings] == [SURPLUS]
    findings = balance(nl, {"o0": 8, "o1": 8})
    assert [f.rule for f in findings] == [STARVED]
    unfed = nl.model_copy(
        update={"nets": {"n1": nl.nets["n1"].model_copy(update={"sources": ()})}}
    )
    assert [f.rule for f in balance(unfed)] == [UNFED]
    fabric = problem(nl).fabric.model_copy(
        update={
            "carriers": {
                "wire": Carrier(id="wire", layer="ground", capacity=Fraction(5))
            }
        }
    )
    assert [f.rule for f in balance(nl, fabric=fabric)] == [CAPACITY]


def test_macros_strategies() -> None:
    cells = {
        "i": cell("i", "IN"),
        "o": cell("o", "OUT"),
        **{f"b{k}": cell(f"b{k}", "BUF") for k in range(1, 4)},
    }
    nl = bank(
        Netlist(pack="gates", library=dict(LIBRARY), cells=cells),
        ["b1", "b2", "b3"],
        "i",
        "o",
        "wire",
        6,
    )
    formed = macros(nl, "bank")
    assert (
        sorted(formed.modules) == ["M1"] and len(formed.modules["M1"].body.cells) == 3
    )
    assert (
        formed.macros["M1_row"].footprint is not None
        and len(formed.modules["M1"].ports) == 6
    )
    assert (
        len(formed.flatten().cells) == len(nl.cells) and formed.flatten().check() == []
    )
    with pytest.raises(IRError, match="no macro strategy"):
        macros(nl, "nowhere")
    gates = from_expressions(["o0 = a & b", "o1 = a & b"])
    assert macros(gates, "bank").modules == {}
    custom = macros(gates, "custom", partition=lambda n, **o: [["g1", "g2"]])
    assert len(custom.modules["M1"].body.cells) == 2 and custom.flatten().check() == []
    with pytest.raises(IRError, match="partition"):
        macros(gates, "custom")
    assert macros(gates, "group").modules == {}
