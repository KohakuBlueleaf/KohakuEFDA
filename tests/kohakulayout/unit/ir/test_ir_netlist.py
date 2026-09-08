"""ir/netlist: checks, hierarchy flattening with port merges, flow order, macro footprints."""

from fractions import Fraction

from kohakulayout.ir import (
    Cell,
    Footprint,
    Group,
    Layout,
    Macro,
    Module,
    ModulePort,
    Net,
    Netlist,
    Pin,
    PinRef,
    Placement,
    Port,
)


def _lib() -> dict[str, Footprint]:
    gate = Footprint(
        id="G",
        width=3,
        height=3,
        ports=(
            Port(id="a", side="W", offset=0, direction="in", carrier="wire"),
            Port(id="b", side="W", offset=2, direction="in", carrier="wire"),
            Port(id="y", side="E", offset=1, direction="out", carrier="wire"),
        ),
    )
    src = Footprint(
        id="I",
        width=1,
        height=1,
        ports=(Port(id="y", side="E", offset=0, direction="out", carrier="wire"),),
    )
    return {"G": gate, "I": src}


def _pin(cell: str, pin: str) -> PinRef:
    return PinRef(cell=cell, pin=pin)


def test_check_names_structural_problems() -> None:
    nl = Netlist(
        library=_lib(),
        cells={
            "two": Cell(id="two", footprint="G", module="M"),
            "gone": Cell(id="gone", footprint="NOPE"),
            "g1": Cell(id="g1", footprint="G", group="bank"),
            "g2": Cell(
                id="g2",
                footprint="G",
                pins=(Pin(id="a", direction="out", carrier="wire", ports=("a",)),),
            ),
            "g3": Cell(id="g3", footprint="G"),
        },
        nets={
            "n1": Net(
                id="n1",
                carrier="wire",
                sources=(_pin("g1", "a"),),
                sinks=(_pin("g1", "b"),),
            ),
            "n2": Net(
                id="n2",
                carrier="wire",
                sources=(_pin("g1", "y"),),
                sinks=(_pin("g1", "b"),),
            ),
            "n3": Net(id="n3", carrier="pipe", sources=(_pin("g3", "y"),), sinks=()),
        },
        groups={"bank": Group(id="bank", members=("g1", "g2"))},
    )
    problems = nl.check()
    assert any("exactly one is required" in p for p in problems)
    assert any("not in the library" in p for p in problems)
    assert any("is an in pin" in p for p in problems)
    assert any("already on net" in p for p in problems)
    assert any("disagree on carrier or direction" in p for p in problems)
    assert any("carries 'wire', not 'pipe'" in p for p in problems)
    assert any("does not name this group" in p for p in problems)


def test_flatten_expands_instances_and_merges_port_nets() -> None:
    body = Netlist(
        cells={"x1": Cell(id="x1", footprint="G"), "x2": Cell(id="x2", footprint="G")},
        nets={
            "m": Net(
                id="m",
                carrier="wire",
                sources=(_pin("x1", "y"),),
                sinks=(_pin("x2", "a"),),
            )
        },
    )
    module = Module(
        id="HA",
        body=body,
        ports=(
            ModulePort(id="a", direction="in", carrier="wire", inner=_pin("x1", "a")),
            ModulePort(id="s", direction="out", carrier="wire", inner=_pin("x1", "y")),
        ),
    )
    nl = Netlist(
        library=_lib(),
        modules={"HA": module},
        cells={
            "i": Cell(id="i", footprint="I"),
            "h": Cell(id="h", module="HA"),
            "g": Cell(id="g", footprint="G"),
        },
        nets={
            "n1": Net(
                id="n1",
                carrier="wire",
                sources=(_pin("i", "y"),),
                sinks=(_pin("h", "a"),),
            ),
            "n2": Net(
                id="n2",
                carrier="wire",
                sources=(_pin("h", "s"),),
                sinks=(_pin("g", "a"),),
            ),
        },
    )
    assert nl.check() == []
    flat = nl.flatten()
    assert sorted(flat.cells) == ["g", "h/x1", "h/x2", "i"]
    assert [str(r) for r in flat.nets["n1"].sinks] == ["h/x1.a"]
    assert "h/m" not in flat.nets, "the inner net driven by the out port merged into n2"
    assert sorted(str(r) for r in flat.nets["n2"].sinks) == ["g.a", "h/x2.a"]
    assert flat.digest() == nl.digest() and flat.is_flat and not nl.is_flat
    assert flat.check() == []


def test_flow_order_lists_the_loop() -> None:
    nl = Netlist(
        library=_lib(),
        cells={"a": Cell(id="a", footprint="G"), "b": Cell(id="b", footprint="G")},
        nets={
            "ab": Net(
                id="ab",
                carrier="wire",
                sources=(_pin("a", "y"),),
                sinks=(_pin("b", "a"),),
            ),
            "ba": Net(
                id="ba",
                carrier="wire",
                sources=(_pin("b", "y"),),
                sinks=(_pin("a", "a"),),
            ),
        },
    )
    order, back = nl.flow_order()
    assert order == ("a", "b") and back == (("b", "a"),)
    assert nl.fanout("a") == 1 and nl.fanin("a") == 1


def test_macro_footprint_is_derived_and_verified() -> None:
    body = Netlist(cells={"x1": Cell(id="x1", footprint="G")})
    module = Module(
        id="ONE",
        body=body,
        ports=(
            ModulePort(id="a", direction="in", carrier="wire", inner=_pin("x1", "a")),
        ),
    )
    fragment = Layout(placements={"x1": Placement(cell="x1", x=0, y=0)})
    nl = Netlist(
        library=_lib(),
        modules={"ONE": module},
        macros={"K": Macro(id="K", module="ONE", layout=fragment)},
        cells={"k": Cell(id="k", macro="K")},
    )
    assert nl.check() == []
    bad = nl.model_copy(
        update={
            "macros": {
                "K": Macro(
                    id="K",
                    module="ONE",
                    layout=Layout(placements={"x1": Placement(cell="x1", x=1, y=0)}),
                )
            }
        }
    )
    assert any("not (0,0)" in p for p in bad.check())
    wrong = nl.model_copy(
        update={
            "macros": {
                "K": Macro(
                    id="K",
                    module="ONE",
                    layout=fragment,
                    footprint=Footprint(id="K", width=9, height=9),
                )
            }
        }
    )
    assert any("disagrees with the derived" in p for p in wrong.check())


def test_rates_are_fractions() -> None:
    net = Net(id="n", carrier="pipe", rate="7/2", sources=(_pin("a", "y"),))
    assert net.rate == Fraction(7, 2)
