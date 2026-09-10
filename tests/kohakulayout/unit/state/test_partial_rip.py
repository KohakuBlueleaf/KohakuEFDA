"""A footprint over one branch of a tree takes up that branch alone: the trunk stays and the cut-off pin is grown again."""

from kohakulayout.ir import Cell, Footprint, Netlist
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem
from tests.kohakulayout.unit.state.router.test_trees import fanout_problem, place_all

BLOCK = Footprint(id="BLOCK", width=1, height=1)


def _problem():
    base = fanout_problem().netlist
    cells = dict(base.cells)
    cells["k"] = Cell(id="k", footprint="BLOCK")
    netlist = Netlist(
        pack="gates", library={**LIBRARY, "BLOCK": BLOCK}, cells=cells, nets=base.nets
    )
    return problem(netlist, width=12, height=8)


def test_a_footprint_over_a_branch_keeps_the_trunk() -> None:
    world = World(_problem(), GatesPhysics(), router=DefaultRouter())
    check = StateCheck().mount(world)
    place_all(world)
    wire = world.wires["n1"]
    trunk, branch = wire.segments[0], wire.segments[-1]
    assert branch.cells[0] in trunk.cells
    target = next(c for c in branch.cells[1:-1] if c not in trunk.cells)
    with world.transaction() as tx:
        assert world.place("k", target[0], target[1], 0) is None
        tx.commit()
    after = world.wires["n1"]
    assert after.segments[0] == trunk
    assert target not in after.cells()
    assert {(10, 1), (10, 5)} <= after.cells()
    assert check.failures == []
