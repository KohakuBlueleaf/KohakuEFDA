"""A carrier with a run limit and no repeater: a short run routes, a run over the limit is refused."""

from fractions import Fraction

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef, Refusal
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem
from kohakulayout.templates.physics.gates.carriers import GatesCarriers

LIMIT = 8


class ShortRuns(GatesCarriers):
    def run_limit(self, carrier: str) -> int | None:
        return LIMIT


class ShortRunPhysics(GatesPhysics):
    def __init__(self) -> None:
        super().__init__()
        self.carriers = ShortRuns()


def _problem():
    netlist = Netlist(
        pack="gates",
        library=dict(LIBRARY),
        cells={
            "a": Cell(
                id="a",
                footprint="IN",
                pins=(Pin(id="y", direction="out", carrier="wire", ports=("y",)),),
            ),
            "y": Cell(
                id="y",
                footprint="OUT",
                pins=(Pin(id="a", direction="in", carrier="wire", ports=("a",)),),
            ),
        },
        nets={
            "n": Net(
                id="n",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="a", pin="y"),),
                sinks=(PinRef(cell="y", pin="a"),),
            )
        },
    )
    return problem(netlist, width=24, height=8)


def test_only_a_run_over_the_limit_is_refused() -> None:
    ctx = Context(
        _problem(), physics=ShortRunPhysics(), seed=1, budget=Budget(units=50)
    )
    world = ctx.world
    with world.transaction():
        assert world.place("a", 0, 3, 0) is None
        far = world.place("y", 23, 3, 0)
        assert isinstance(far, Refusal) and "exceeds the limit" in far.detail
        assert world.place("y", 8, 3, 0) is None
        assert "n" in world.wires
        assert all(len(s.cells) <= LIMIT for s in world.wires["n"].segments)
