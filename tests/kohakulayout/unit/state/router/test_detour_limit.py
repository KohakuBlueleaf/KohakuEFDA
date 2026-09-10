"""A search gives up past its detour: the span across stretched by ``detour`` plus ``slack``, on both kernels alike."""

from fractions import Fraction

import pytest

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef
from kohakulayout.state import DefaultRouter
from kohakulayout.templates.physics.gates import LIBRARY, problem


def _problem():
    netlist = Netlist(
        pack="gates",
        library=dict(LIBRARY),
        cells={
            "b": Cell(
                id="b",
                footprint="IN",
                pins=(Pin(id="y", direction="out", carrier="wire", ports=("y",)),),
            ),
            "z": Cell(
                id="z",
                footprint="OUT",
                pins=(Pin(id="a", direction="in", carrier="wire", ports=("a",)),),
            ),
            "g": Cell(id="g", footprint="NOT"),
        },
        nets={
            "far": Net(
                id="far",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="b", pin="y"),),
                sinks=(PinRef(cell="z", pin="a"),),
            ),
        },
    )
    return problem(netlist, width=20, height=9)


@pytest.mark.parametrize("kernel", ["python", "native"])
def test_a_tight_detour_refuses_the_long_way_round(kernel: str) -> None:
    tight = DefaultRouter(detour=1.0, slack=0.0)
    ctx = Context(
        _problem(),
        physics=None,
        seed=1,
        budget=Budget(units=50),
        kernel=kernel,
        router=tight,
    )
    world = ctx.world
    with world.transaction() as tx:
        assert world.place("g", 9, 3) is None
        assert world.place("b", 0, 4) is None
        refusal = world.place("z", 19, 4)
        assert refusal is not None and refusal.stage == "route", refusal
        tx.commit()
    loose = DefaultRouter(detour=2.5, slack=16.0)
    ctx = Context(
        _problem(),
        physics=None,
        seed=1,
        budget=Budget(units=50),
        kernel=kernel,
        router=loose,
    )
    world = ctx.world
    with world.transaction() as tx:
        assert world.place("g", 9, 3) is None
        assert world.place("b", 0, 4) is None
        assert world.place("z", 19, 4) is None
        assert "far" in world.wires
        tx.commit()
