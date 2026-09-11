"""The routed evaluator: a split shared by acceptance, a merge, a unit that filters, a link off the grid, a dangling run."""

from fractions import Fraction

from kohakulayout.flow import Routed, evaluate
from kohakulayout.ir import (
    Cell,
    Footprint,
    Layout,
    Net,
    Netlist,
    Pin,
    PinRef,
    Placement,
    Port,
    Segment,
    Unit,
    Wire,
)
from kohakulayout.physics import DefaultFlow, Made

SRC = Footprint(
    id="SRC",
    width=1,
    height=1,
    ports=(Port(id="y", side="E", offset=0, direction="out", carrier="wire"),),
)
SINK = Footprint(
    id="SINK",
    width=1,
    height=1,
    ports=(Port(id="a", side="W", offset=0, direction="in", carrier="wire"),),
)
JUNCTION = Footprint(id="J", width=1, height=1, rotations=(0,))


def _cell(cell_id: str, fp: Footprint) -> Cell:
    port = fp.ports[0]
    return Cell(
        id=cell_id,
        footprint=fp.id,
        pins=(
            Pin(id=port.id, direction=port.direction, carrier="wire", ports=(port.id,)),
        ),
    )


def _netlist() -> Netlist:
    return Netlist(
        library={"SRC": SRC, "SINK": SINK, "J": JUNCTION},
        cells={
            "s": _cell("s", SRC),
            "a": _cell("a", SINK),
            "b": _cell("b", SINK),
        },
        nets={
            "n": Net(
                id="n",
                carrier="wire",
                rate=Fraction(10),
                sources=(PinRef(cell="s", pin="y"),),
                sinks=(PinRef(cell="a", pin="a"), PinRef(cell="b", pin="a")),
            )
        },
    )


def _layout() -> Layout:
    """s at (0,0) feeds (1,0)..(3,0); a splitter at (3,0) branches to a at (5,0) and b at (5,2)."""
    return Layout(
        placements={
            "s": Placement(cell="s", x=0, y=0),
            "a": Placement(cell="a", x=5, y=0),
            "b": Placement(cell="b", x=5, y=2),
        },
        wires={
            "n": Wire(
                net="n",
                segments=(
                    Segment(
                        carrier="wire", layer="ground", cells=((1, 0), (2, 0), (3, 0))
                    ),
                    Segment(carrier="wire", layer="ground", cells=((3, 0), (4, 0))),
                    Segment(
                        carrier="wire",
                        layer="ground",
                        cells=((3, 0), (3, 1), (3, 2), (4, 2)),
                    ),
                ),
                units=("j",),
            )
        },
        units={"j": Unit(id="j", kind="J", footprint="J", x=3, y=0, owner="net:n")},
    )


class Taking(DefaultFlow):
    """``a`` takes up to ``cap``; the source makes ``rate`` of ``ore``."""

    evaluator = "routed"

    def __init__(self, cap: Fraction, rate: Fraction = Fraction(10)) -> None:
        self.cap = cap
        self.rate = rate

    def commodity(self, cell, pin):
        return "ore"

    def accept(self, cell, seen, capacities, room):
        if cell.id == "a":
            return {"a": min(self.cap, capacities["a"])}
        return dict(capacities)

    def produce(self, cell, inputs, accepts):
        if cell.id == "s":
            return Made(outputs={"y": {"ore": self.rate}}, load=Fraction(1))
        return Made(outputs={}, load=sum(_total(m) for m in inputs.values()) / 10)


def _total(mix):
    return sum(mix.values(), Fraction(0))


def test_a_split_shares_evenly_and_a_capped_sink_hands_the_rest_on() -> None:
    result = evaluate(
        _netlist(), Taking(Fraction(100)), evaluator="routed", layout=_layout()
    )
    assert result.converged
    assert result.at("a", "a") == Fraction(5) and result.at("b", "a") == Fraction(5)
    capped = evaluate(
        _netlist(), Taking(Fraction(2)), evaluator="routed", layout=_layout()
    )
    assert capped.at("a", "a") == Fraction(2) and capped.at("b", "a") == Fraction(8)
    assert capped.cells["a"].received == {"a": {"ore": Fraction(2)}}
    assert capped.cells["b"].load == Fraction(8, 10)
    runs = {r.cells: r.total for r in capped.runs.values() if r.cells}
    assert runs[((1, 0), (2, 0), (3, 0))] == Fraction(10)


def test_the_declared_rate_flows_without_produce_and_a_unit_may_filter() -> None:
    plain = DefaultFlow()
    result = evaluate(_netlist(), plain, evaluator="routed", layout=_layout())
    assert result.converged and result.at("a", "a") == Fraction(5)
    assert set(result.cells["a"].received["a"]) == {"s.y"}

    class Shut(Taking):
        def passes(self, unit, commodity):
            return unit.id != "j"

    shut = evaluate(
        _netlist(), Shut(Fraction(100)), evaluator="routed", layout=_layout()
    )
    assert shut.at("a", "a") == 0 and shut.at("b", "a") == 0


def test_a_link_joins_pins_off_the_grid_and_a_dangling_run_carries() -> None:
    netlist = _netlist().model_copy(
        update={
            "cells": {
                **_netlist().cells,
                "c": Cell(id="c", footprint="J", pins=()),
            }
        }
    )

    class Linked(Taking):
        def links(self, netlist):
            return (("a", "through", "c", "got"),)

        def produce(self, cell, inputs, accepts):
            if cell.id == "a":
                return Made(outputs={"through": dict(inputs["a"])})
            return super().produce(cell, inputs, accepts)

    layout = _layout().model_copy(
        update={
            "placements": {**_layout().placements, "c": Placement(cell="c", x=7, y=7)}
        }
    )
    result = evaluate(netlist, Linked(Fraction(100)), evaluator="routed", layout=layout)
    assert result.converged
    assert result.cells["c"].received == {"got": {"ore": Fraction(5)}}
    dangling = _layout().model_copy(
        update={
            "wires": {
                "n": Wire(
                    net="n",
                    segments=(
                        Segment(
                            carrier="wire",
                            layer="ground",
                            cells=((1, 0), (2, 0), (3, 0)),
                        ),
                        Segment(carrier="wire", layer="ground", cells=((3, 0), (4, 0))),
                        Segment(carrier="wire", layer="ground", cells=((3, 0), (3, 1))),
                    ),
                    units=("j",),
                )
            }
        }
    )
    loose = evaluate(
        _netlist(), Taking(Fraction(100)), evaluator="routed", layout=dangling
    )
    assert loose.at("a", "a") == Fraction(5)
    assert Routed().max_rounds == 1000


def test_a_crossing_unit_keeps_each_way_of_travel_apart() -> None:
    """A wire runs south through a crossing and back north through it; nothing leaks between the ways."""
    netlist = Netlist(
        library={"SRC": SRC, "SINK": SINK, "J": JUNCTION},
        cells={"s": _cell("s", SRC), "a": _cell("a", SINK)},
        nets={
            "n": Net(
                id="n",
                carrier="wire",
                rate=Fraction(10),
                sources=(PinRef(cell="s", pin="y"),),
                sinks=(PinRef(cell="a", pin="a"),),
            )
        },
    )
    layout = Layout(
        placements={
            "s": Placement(cell="s", x=0, y=0),
            "a": Placement(cell="a", x=2, y=4),
        },
        wires={
            "n": Wire(
                net="n",
                segments=(
                    Segment(
                        carrier="wire",
                        layer="ground",
                        cells=((1, 0), (2, 0), (2, 1), (2, 2)),
                    ),
                    Segment(
                        carrier="wire",
                        layer="ground",
                        cells=((2, 2), (2, 3), (3, 3), (3, 2)),
                    ),
                    Segment(
                        carrier="wire",
                        layer="ground",
                        cells=((3, 2), (2, 2), (1, 2), (1, 3), (1, 4)),
                    ),
                ),
                units=("x",),
            )
        },
        units={"x": Unit(id="x", kind="J", footprint="J", x=2, y=2, owner="net:n")},
    )

    class Crossing(Taking):
        def crosses(self, unit):
            return unit.id == "x"

    result = evaluate(
        netlist,
        Crossing(Fraction(100)),
        evaluator="routed",
        layout=layout,
        oriented=True,
    )
    assert result.converged and result.at("a", "a") == Fraction(10)
    ways = {
        r.source.rsplit(":", 1)[-1] for r in result.runs.values() if "/x:" in r.source
    }
    assert ways == {"S", "W"}
