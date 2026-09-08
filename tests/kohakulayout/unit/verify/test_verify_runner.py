"""Structural findings, the rule runner and the report."""

from kohakulayout.engine import Context
from kohakulayout.ir import Layout, Placement
from kohakulayout.templates.physics.gates import from_expressions, problem
from kohakulayout.verify import geometry, missing, report, run, structural, unrouted


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
