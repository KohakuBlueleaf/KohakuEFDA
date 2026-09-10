"""A wire may run through a field emitter's cell: the emitter is removed, the cover redone; with nowhere left to cover from, the route is refused."""

from fractions import Fraction

import pytest

from kohakulayout._rust import HAS_RUST
from kohakulayout.ir import Cell, Footprint, Net, Netlist, Pin, PinRef
from kohakulayout.physics import UnitPlacement
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.templates.physics.gates import LIBRARY, GatesPowerPhysics, problem
from kohakulayout.templates.physics.gates.library import VDD

KERNELS = ("python", "native") if HAS_RUST else ("python",)
BLOCK = Footprint(id="BLOCK", width=1, height=1)
CORRIDOR_WALL = [(x, 3) for x in range(4, 11)]
REACH_OF_G = (
    [(x, y) for x in range(2) for y in range(3)]
    + [(x, 3) for x in range(4)]
    + [(x, y) for x in range(4, 7) for y in range(3)]
)


def _problem(blocks: list[tuple[int, int]]):
    cells = {
        "a": Cell(
            id="a",
            footprint="IN",
            pins=(Pin(id="y", direction="out", carrier="wire", ports=("y",)),),
        ),
        "o": Cell(
            id="o",
            footprint="OUT",
            pins=(Pin(id="a", direction="in", carrier="wire", ports=("a",)),),
        ),
        "g": Cell(id="g", footprint="NOT"),
    }
    for i, _ in enumerate(blocks):
        cells[f"k{i}"] = Cell(id=f"k{i}", footprint="BLOCK")
    netlist = Netlist(
        pack="gates-power",
        library={**LIBRARY, "BLOCK": BLOCK},
        cells=cells,
        nets={
            "n": Net(
                id="n",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="a", pin="y"),),
                sinks=(PinRef(cell="o", pin="a"),),
            )
        },
    )
    return problem(netlist, power=True, width=14, height=5)


def _emitters(world: World) -> dict[str, tuple[int, int]]:
    return {
        uid: (u.x, u.y)
        for uid, u in world.units.items()
        if u.owner.startswith("field:")
    }


def _world(kernel: str, blocks: list[tuple[int, int]]) -> tuple[World, StateCheck, str]:
    """The corridor board: a gate powered by an emitter standing on the only row from ``a`` to ``o``."""
    world = World(
        _problem(blocks), GatesPowerPhysics(), kernel=kernel, router=DefaultRouter()
    )
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        spot = UnitPlacement(kind="power", footprint=VDD, x=6, y=4, owner="field:power")
        assert world.place_unit(spot, "vdd") is None
        assert world.place("g", 2, 0, 0) is None
        assert _emitters(world) == {"vdd": (6, 4)}
        for i, (x, y) in enumerate(blocks):
            assert world.place(f"k{i}", x, y, 0) is None
        assert world.place("a", 0, 4, 0) is None
        tx.commit()
    return world, check, "vdd"


@pytest.mark.parametrize("kernel", KERNELS)
def test_a_wire_moves_the_emitter_in_its_way_and_the_gate_stays_covered(
    kernel: str,
) -> None:
    world, check, vdd = _world(kernel, CORRIDOR_WALL)
    with world.transaction() as tx:
        assert world.place("o", 13, 4, 0) is None
        tx.commit()
    assert (6, 4) in world.wires["n"].cells()
    after = _emitters(world)
    assert vdd not in after and len(after) == 1 and (6, 4) not in after.values()
    covered = world.field_coverage("power")
    assert any((x, y) in covered for x in (2, 3) for y in (0, 1, 2))
    assert check.failures == []


@pytest.mark.parametrize("kernel", KERNELS)
def test_a_wire_leaves_the_emitter_when_nothing_else_could_cover(kernel: str) -> None:
    world, check, vdd = _world(kernel, CORRIDOR_WALL + REACH_OF_G)
    with world.transaction() as tx:
        refusal = world.place("o", 13, 4, 0)
        assert refusal is not None and refusal.stage == "route", refusal
        assert "displaced an emitter" in refusal.detail
        tx.commit()
    assert _emitters(world) == {vdd: (6, 4)}
    assert "n" not in world.wires
    assert check.failures == []
