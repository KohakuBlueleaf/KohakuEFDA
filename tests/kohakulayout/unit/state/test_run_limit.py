"""A run limit without a repeater: a run over it is refused, and runs count between units."""

from fractions import Fraction

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef, Refusal
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem
from kohakulayout.templates.physics.gates.carriers import GatesCarriers
from kohakulayout.templates.physics.gates.library import JUMPER

LIMIT = 8


class ShortRuns(GatesCarriers):
    def run_limit(self, carrier: str) -> int | None:
        return LIMIT


class ShortRunPhysics(GatesPhysics):
    def __init__(self) -> None:
        super().__init__()
        self.carriers = ShortRuns()


def _source(id: str) -> Cell:
    return Cell(
        id=id,
        footprint="IN",
        pins=(Pin(id="y", direction="out", carrier="wire", ports=("y",)),),
    )


def _sink(id: str) -> Cell:
    return Cell(
        id=id,
        footprint="OUT",
        pins=(Pin(id="a", direction="in", carrier="wire", ports=("a",)),),
    )


def _net(id: str, source: str, sink: str) -> Net:
    return Net(
        id=id,
        carrier="wire",
        rate=Fraction(1),
        sources=(PinRef(cell=source, pin="y"),),
        sinks=(PinRef(cell=sink, pin="a"),),
    )


def _problem(crossed: bool = False):
    cells = {"a": _source("a"), "y": _sink("y")}
    nets = {"n": _net("n", "a", "y")}
    if crossed:
        cells |= {"b": _source("b"), "z": _sink("z")}
        nets["m"] = _net("m", "b", "z")
    return problem(
        Netlist(pack="gates", library=dict(LIBRARY), cells=cells, nets=nets),
        width=24,
        height=7,
    )


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


def test_a_run_counts_between_unit_cells() -> None:
    ctx = Context(
        _problem(crossed=True),
        physics=ShortRunPhysics(),
        seed=1,
        budget=Budget(units=50),
    )
    world = ctx.world
    with world.transaction():
        assert world.place("b", 7, 0, 0) is None
        assert world.place("z", 9, 6, 0) is None
        assert [list(s.cells) for s in world.wires["m"].segments] == [
            [(8, y) for y in range(7)]
        ]
        assert world.place("a", 0, 3, 0) is None
        far = world.place("y", 18, 3, 0)
        assert isinstance(far, Refusal) and "exceeds the limit" in far.detail
        assert world.place("y", 16, 3, 0) is None
        cells = list(world.wires["n"].segments[0].cells)
        assert cells == [(x, 3) for x in range(1, 16)]
        jumpers = [u for u in world.units.values() if u.footprint == JUMPER.id]
        assert [(u.x, u.y) for u in jumpers] == [(8, 3)]
