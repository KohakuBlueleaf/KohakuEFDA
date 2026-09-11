"""Structural findings, the rule runner and the report."""

from kohakulayout.engine import Context
from kohakulayout.ir import Layout, Placement, Refusal, Segment, Wire
from kohakulayout.templates.physics.gates import (
    GatesPhysics,
    from_expressions,
    problem,
)
from kohakulayout.verify import (
    GEOMETRY,
    LEGAL,
    OCCUPANCY,
    geometry,
    missing,
    report,
    run,
    structural,
    unrouted,
)


def test_structural_names_every_gap() -> None:
    netlist = from_expressions("y = a & b")
    fabric = problem(netlist, width=16, height=8).fabric
    layout = Layout(
        placements={
            "a": Placement(cell="a", x=0, y=0),
            "b": Placement(cell="b", x=0, y=0),
            "g1": Placement(cell="g1", x=14, y=6),
        }
    )
    found = structural(layout, netlist, fabric)
    rules = [f.rule for f in found]
    assert rules.count("kl.geometry") == 2
    assert [f.subject for f in missing(layout, netlist)] == ["cell:y"]
    assert len(unrouted(layout, netlist)) == 3
    assert all(f.severity == "error" for f in found)
    assert geometry(Layout(), netlist, fabric) == ()


def test_runner_adds_the_pack_rules_and_report_reads() -> None:
    netlist = from_expressions("y = a & b")
    ctx = Context(problem(netlist, width=16, height=8), router=None)
    world = ctx.world
    with world.transaction() as tx:
        world.place("a", 0, 0)
        world.place("b", 0, 2)
        world.place("g1", 4, 0)
        tx.commit()
    off_edge = world.freeze().model_copy(
        update={"placements": {**world.placements, "y": Placement(cell="y", x=9, y=1)}}
    )
    found = run(world, off_edge, {})
    assert "gates.edge" in {f.rule for f in found}
    text = report(ctx.assess())
    assert text.startswith("assessment ") and "incomplete" in text
    assert "kl.unrouted net:n1" in text and "placed = 3" in text


def _placed_world():
    netlist = from_expressions("y = a & b")
    ctx = Context(problem(netlist, width=16, height=8), router=None)
    world = ctx.world
    with world.transaction() as tx:
        world.place("a", 0, 0)
        world.place("b", 0, 2)
        world.place("g1", 4, 0)
        tx.commit()
    return world


def test_two_occupants_on_one_cell_are_a_finding() -> None:
    world = _placed_world()
    frozen = world.freeze()
    stacked = frozen.model_copy(
        update={"placements": {**frozen.placements, "b": Placement(cell="b", x=0, y=0)}}
    )
    found = [f for f in run(world, stacked, {}) if f.rule == OCCUPANCY]
    assert found and all(f.severity == "error" for f in found)
    assert {f.subject for f in found} == {"cell:a"}
    assert not [f for f in run(world, frozen, {}) if f.rule == OCCUPANCY]


def test_a_placement_the_boundaries_refuse_is_a_finding() -> None:
    class Strict(GatesPhysics):
        def __init__(self) -> None:
            super().__init__()
            boundaries = self.boundaries

            def legal(world, placement):
                if placement.cell == "g1":
                    return Refusal(
                        stage="legal", subject="cell:g1", detail="no gates here"
                    )
                return None

            boundaries.legal = legal

    netlist = from_expressions("y = a & b")
    ctx = Context(problem(netlist, width=16, height=8), physics=Strict(), router=None)
    world = ctx.world
    with world.transaction() as tx:
        world.place("a", 0, 0)
        tx.commit()
    layout = world.freeze().model_copy(
        update={
            "placements": {**world.placements, "g1": Placement(cell="g1", x=4, y=0)}
        }
    )
    found = [f for f in run(world, layout, {}) if f.rule == LEGAL]
    assert [(f.subject, f.message) for f in found] == [("cell:g1", "g1: no gates here")]


def test_a_broken_wire_is_a_geometry_finding() -> None:
    world = _placed_world()
    frozen = world.freeze()
    net_id = next(iter(world.netlist.nets))
    broken = frozen.model_copy(
        update={
            "wires": {
                net_id: Wire(
                    net=net_id,
                    segments=(
                        Segment(carrier="wire", layer="ground", cells=((1, 1), (3, 1))),
                    ),
                ),
            }
        }
    )
    found = [f for f in run(world, broken, {}) if f.rule == GEOMETRY]
    assert any("not a contiguous path" in f.message for f in found)
