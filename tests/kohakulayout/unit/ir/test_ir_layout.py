"""ir/layout.py: internal checks, geometry checks against a problem, instance flattening."""

from pathlib import Path

from kohakulayout.ir import Layout, Placement, Segment, Unit, Wire, parse_text

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_internal_checks() -> None:
    layout = Layout(
        placements={"a": Placement(cell="b", x=0, y=0)},
        wires={
            "n": Wire(
                net="n",
                segments=(
                    Segment(carrier="wire", layer="ground", cells=((0, 0), (2, 0))),
                ),
            )
        },
        units={"u": Unit(id="u", footprint="J", x=0, y=0, owner="nowhere")},
    )
    problems = layout.check()
    assert any("names 'b'" in p for p in problems)
    assert any("not a contiguous path" in p for p in problems)
    assert any("not net:, field: or cell:" in p for p in problems)
    two = Layout(
        wires={
            "n": Wire(
                net="n",
                segments=(
                    Segment(carrier="w", layer="g", cells=((0, 0),)),
                    Segment(carrier="w", layer="g", cells=((5, 5),)),
                ),
            )
        }
    )
    assert any("one connected tree" in p for p in two.check())


def test_geometry_checks_against_the_problem() -> None:
    levels = parse_text((FIXTURES / "two_gates.kl").read_text(encoding="utf-8"))
    problem, layout = levels.problem, levels.layout
    assert layout.check_against(problem.netlist, problem.fabric) == []
    moved = layout.model_copy(
        update={"placements": {**layout.placements, "b": Placement(cell="b", x=6, y=3)}}
    )
    problems = moved.check_against(problem.netlist, problem.fabric)
    assert any("overlaps" in p for p in problems)
    assert any("does not reach b.y" in p for p in problems)
    outside = layout.model_copy(
        update={
            "placements": {**layout.placements, "y": Placement(cell="y", x=99, y=3)}
        }
    )
    assert any(
        "leaves the grid" in p
        for p in outside.check_against(problem.netlist, problem.fabric)
    )
    assert layout.extent(problem.netlist) == (0, 2, 13, 3)


def test_instance_flattening_rotates_the_fragment() -> None:
    levels = parse_text((FIXTURES / "half_adder_hier.kl").read_text(encoding="utf-8"))
    problem, layout = levels.problem, levels.layout
    assert not layout.is_flat
    flat = layout.flatten(problem.netlist)
    assert flat.is_flat and sorted(flat.placements) == ["h1/x1", "h1/x2", "i1", "i2"]
    assert flat.placements["h1/x1"].rot == 90 and flat.placements["h1/x2"].rot == 90
    assert flat.check() == []
    assert flat.check_against(problem.netlist, problem.fabric) == []
    assert flat.wires["h1/m1"].segments[0].cells == ((5, 3), (6, 3))
    assert flat.placements["h1/x2"] == Placement(cell="h1/x2", x=4, y=4, rot=90)
