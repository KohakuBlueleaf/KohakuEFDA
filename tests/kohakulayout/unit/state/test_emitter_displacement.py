"""A unit a route needs may take a field emitter's cell: the emitter moves and what it served stays covered."""

from fractions import Fraction

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Cell, Footprint, Net, Netlist, Pin, PinRef
from kohakulayout.state.router.units import place
from kohakulayout.templates.physics.gates import LIBRARY, problem

JUNCTION = Footprint(id="J", width=1, height=1)


def _problem():
    netlist = Netlist(
        pack="gates-power",
        library=dict(LIBRARY),
        cells={
            "a": Cell(
                id="a",
                footprint="IN",
                pins=(Pin(id="y", direction="out", carrier="wire", ports=("y",)),),
            ),
            "g": Cell(
                id="g",
                footprint="NOT",
                pins=(
                    Pin(id="a", direction="in", carrier="wire", ports=("a",)),
                    Pin(id="y", direction="out", carrier="wire", ports=("y",)),
                ),
            ),
        },
        nets={
            "n": Net(
                id="n",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="a", pin="y"),),
                sinks=(PinRef(cell="g", pin="a"),),
            )
        },
    )
    return problem(netlist, power=True, width=16, height=10)


def _emitters(world) -> dict[str, tuple[int, int]]:
    return {
        uid: (u.x, u.y)
        for uid, u in world.units.items()
        if u.owner.startswith("field:")
    }


def test_a_junction_displaces_the_emitter_and_the_gate_stays_powered() -> None:
    ctx = Context(_problem(), physics=None, seed=1, budget=Budget(units=50))
    world = ctx.world
    with world.transaction() as tx:
        assert world.place("g", 6, 3, 0) is None
        before = _emitters(world)
        assert len(before) == 1
        ((emitter, spot),) = before.items()
        placed = place(world, "n", JUNCTION, spot, "split unit")
        assert isinstance(placed, str), placed
        assert (world.units[placed].x, world.units[placed].y) == spot
        assert emitter not in world.units
        after = _emitters(world)
        assert len(after) == 1 and spot not in after.values()
        covered = world.field_coverage("power")
        assert any(c in covered for c in ((6, 3), (7, 3), (6, 5), (7, 5)))
        tx.commit()
    with world.transaction() as tx:
        assert world.place("a", 1, 4, 0) is None
        assert "n" in world.wires
        tx.commit()
