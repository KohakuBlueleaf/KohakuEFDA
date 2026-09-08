"""Builders: a netlist without hand-wiring pins."""

from fractions import Fraction

import pytest

from kohakulayout.errors import IRError
from kohakulayout.ir import Constraint, Footprint, Netlist, Pin, Port
from kohakulayout.templates.physics.gates import LIBRARY
from kohakulayout.utils import bank, cell, chain, entries, fanout, hub, instantiate
from kohakulayout.utils.build import add_cells, next_id, pin_for
from kohakulayout.utils.passes import macros


def base(*ids: tuple[str, str]) -> Netlist:
    return Netlist(
        pack="gates", library=dict(LIBRARY), cells={i: cell(i, fp) for i, fp in ids}
    )


def test_chain_fanout_and_entries() -> None:
    nl = base(("i", "IN"), ("g1", "NOT"), ("g2", "BUF"), ("o", "OUT"))
    nl = chain(nl, ["i", "g1", "g2", "o"], "wire", 5)
    assert sorted(nl.nets) == ["n1", "n2", "n3"] and nl.nets["n2"].rate == Fraction(5)
    assert (
        str(nl.nets["n1"].sources[0]) == "i.y" and str(nl.nets["n3"].sinks[0]) == "o.a"
    )
    nl = fanout(base(("i", "IN"), ("a", "BUF"), ("b", "BUF")), "i", ["a", "b"], "wire")
    assert len(nl.nets["n1"].sinks) == 2 and nl.check() == []
    nl = entries(base(("a", "BUF")), "W", "wire", ["a"], 3)
    assert nl.nets["n1"].outside == "W" and nl.nets["n1"].sources == ()
    assert next_id(nl, "n") == "n2"
    with pytest.raises(IRError, match="no in pin"):
        pin_for(nl, "a", "in", "clk")
    with pytest.raises(IRError, match="exists"):
        add_cells(nl, [cell("a", "BUF")])


def test_bank_hub_and_instantiate() -> None:
    nl = base(("i", "IN"), ("o", "OUT"), ("b1", "BUF"), ("b2", "BUF"))
    nl = bank(nl, ["b1", "b2"], "i", "o", "wire", 4)
    assert [len(n.sources) for n in nl.nets.values()] == [1, 2] and nl.check() == []
    fp = Footprint(
        id="HUB",
        width=4,
        height=4,
        ports=(
            Port(id="p1", side="N", offset=0, direction="in", carrier="wire"),
            Port(id="p2", side="S", offset=0, direction="out", carrier="wire"),
        ),
    )
    nl = hub(nl, "h", fp, None, "hub")
    assert nl.cells["h"].constraint == Constraint(kind="hub") and "HUB" in nl.library
    assert [p.id for p in nl.pins_of("h")] == ["p1", "p2"]
    nl = hub(
        nl, "h2", fp, [Pin(id="only", direction="in", carrier="wire", ports=("p1",))]
    )
    assert [p.id for p in nl.pins_of("h2")] == ["only"]
    formed = macros(nl, "bank")
    assert "M1" in formed.modules and "M1_row" in formed.macros
    more = instantiate(
        formed, "M1_row", "m2", b1_a="n1", b2_a="n1", b1_y="n2", b2_y="n2"
    )
    assert len(more.nets["n1"].sinks) == 4 and len(more.nets["n2"].sources) == 4
    assert (
        more.check() == []
        and len(more.flatten().cells) == len(formed.flatten().cells) + 2
    )
    with pytest.raises(IRError, match="no port"):
        instantiate(formed, "M1", "m3", nope="n1")
    with pytest.raises(IRError, match="no module"):
        instantiate(formed, "M9", "m3")
