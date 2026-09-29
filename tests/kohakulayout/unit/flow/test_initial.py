"""Explicit initial guesses distinguish cold and sustained cyclic flow without injecting supply."""

from fractions import Fraction

import pytest

from kohakulayout.flow import Routed, evaluate
from kohakulayout.ir import (
    Cell,
    Footprint,
    Layout,
    Net,
    Netlist,
    PinRef,
    Placement,
    Port,
    Segment,
    Wire,
)
from kohakulayout.physics import DefaultFlow, Made


class Circulating(DefaultFlow):
    """Move at most one token per iteration; an optional stopped cell drains the loop."""

    evaluator = "routed"

    def __init__(self, stopped: str | None = None) -> None:
        self.stopped = stopped

    def commodity(self, cell, pin):
        return "token"

    def produce(self, cell, inputs, accepts):
        available = sum(
            (v for mix in inputs.values() for v in mix.values()), Fraction(0)
        )
        rate = Fraction(0) if cell.id == self.stopped else min(Fraction(1), available)
        return Made(outputs={"out": {"token": rate}}, load=rate)


def circuit() -> tuple[Netlist, Layout]:
    footprint = Footprint(
        id="relay",
        width=1,
        height=1,
        ports=(
            Port(id="in", side="W", offset=0, direction="in", carrier="wire"),
            Port(id="out", side="E", offset=0, direction="out", carrier="wire"),
        ),
    )
    netlist = Netlist(
        library={"relay": footprint},
        cells={key: Cell(id=key, footprint="relay") for key in ("a", "b")},
        nets={
            key: Net(
                id=key,
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell=source, pin="out"),),
                sinks=(PinRef(cell=sink, pin="in"),),
            )
            for key, source, sink in (("forward", "a", "b"), ("return", "b", "a"))
        },
    )
    paths = {
        "forward": ((2, 1), (3, 1), (4, 1)),
        "return": (
            (6, 1),
            (6, 2),
            (6, 3),
            (5, 3),
            (4, 3),
            (3, 3),
            (2, 3),
            (1, 3),
            (0, 3),
            (0, 2),
            (0, 1),
        ),
    }
    layout = Layout(
        placements={
            "a": Placement(cell="a", x=1, y=1),
            "b": Placement(cell="b", x=5, y=1),
        },
        wires={
            key: Wire(
                net=key,
                segments=(Segment(carrier="wire", layer="ground", cells=cells),),
            )
            for key, cells in paths.items()
        },
    )
    return netlist, layout


def test_cyclic_flow_has_distinct_empty_and_declared_initial_states() -> None:
    netlist, layout = circuit()
    cold = evaluate(netlist, Circulating(), evaluator="routed", layout=layout)
    warm = evaluate(
        netlist, Circulating(), evaluator="routed", layout=layout, initial="declared"
    )
    assert cold.converged and warm.converged
    assert cold.cells["a"].load == 0
    assert warm.cells["a"].load == warm.cells["b"].load == 1
    assert all(run.total <= 1 for run in warm.runs.values())


def test_declared_initial_guess_does_not_sustain_a_broken_loop() -> None:
    netlist, layout = circuit()
    result = evaluate(
        netlist,
        Circulating(stopped="b"),
        evaluator="routed",
        layout=layout,
        initial="declared",
    )
    assert result.converged
    assert result.cells["a"].load == result.cells["b"].load == 0
    assert all(run.total == 0 for run in result.runs.values())


def test_invalid_initial_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="initial flow"):
        Routed(initial="imaginary")
