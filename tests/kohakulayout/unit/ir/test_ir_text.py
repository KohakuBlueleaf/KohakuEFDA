"""ir/text: golden fixtures, the four round-trip properties by seed, and parse errors that name the line."""

from pathlib import Path

import pytest
from kl_gen import random_layout, random_problem

from kohakulayout.errors import TextError
from kohakulayout.ir import Layout, Netlist, Problem, parse_text, write
from kohakulayout.ir.json import loads

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
GOLDEN = sorted(p for p in FIXTURES.glob("*.kl") if not p.name.endswith(".flat.kl"))


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: p.stem)
def test_fixture_round_trips(path: Path) -> None:
    levels = parse_text(path.read_text(encoding="utf-8"))
    for level in (
        levels.problem,
        levels.netlist if levels.problem is None else None,
        levels.layout,
        levels.assessment,
    ):
        if level is None:
            continue
        assert level.check() == [], level.check()
        context = levels.problem
        text = write(level, context)
        again = parse_text(
            text, context=levels if not isinstance(level, Problem) else None
        )
        back = again.pick(type(level))
        assert back == level, f"{path.name}: {level.level} text round trip"
        assert write(back, context) == text
        assert loads(level.to_json()) == level
        assert back.digest() == level.digest()


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: p.stem)
def test_goldens_match_the_writer(path: Path) -> None:
    """The checked-in JSON and flat text are what the tool emits today; regenerate with kl when a change is meant."""
    levels = parse_text(path.read_text(encoding="utf-8"))
    level = levels.problem or levels.netlist or levels.layout or levels.assessment
    json_golden = path.with_suffix(".json")
    flat_golden = path.with_suffix(".flat.kl")
    assert (
        json_golden.exists()
    ), f"missing {json_golden.name}: run kl json {path.name} -o {json_golden.name}"
    assert json_golden.read_text(encoding="utf-8") == level.to_json() + "\n"
    flat = (
        level.model_copy(update={"netlist": level.netlist.flatten()})
        if isinstance(level, Problem)
        else level
    )
    assert flat_golden.read_text(encoding="utf-8") == write(flat, levels.problem)


def test_hierarchy_and_flat_share_a_digest() -> None:
    levels = parse_text((FIXTURES / "half_adder_hier.kl").read_text(encoding="utf-8"))
    netlist = levels.netlist
    assert netlist.digest() == netlist.flatten().digest()
    assert (
        levels.problem.digest()
        == levels.problem.model_copy(update={"netlist": netlist.flatten()}).digest()
    )


@pytest.mark.parametrize("seed", range(24))
def test_random_problems_round_trip(seed: int) -> None:
    problem = random_problem(seed, n_cells=4 + seed % 5, hier=seed % 3 == 0)
    assert problem.check() == [], problem.check()
    text = write(problem)
    back = parse_text(text).problem
    assert back == problem
    assert write(back) == text
    assert loads(problem.to_json()) == problem
    assert (
        back.digest()
        == problem.digest()
        == problem.model_copy(update={"netlist": problem.netlist.flatten()}).digest()
    )
    layout = random_layout(seed, problem)
    assert layout.check() == []
    for context in (None, problem):
        ltext = write(layout, context)
        levels = parse_text(
            ltext, context=parse_text(text) if context is not None else None
        )
        assert levels.layout == layout, ltext
        assert write(levels.layout, context) == ltext
    assert loads(layout.to_json()) == layout


def test_parse_errors_name_the_line() -> None:
    with pytest.raises(TextError) as info:
        parse_text("kl 1\ncell a\n")
    assert "line 2" in str(info.value)
    with pytest.raises(TextError) as info:
        parse_text("kl 1\nlib G 1x1 { y out wire E0 }\ncell a NOPE\n")
    assert "not a footprint, module or macro" in str(info.value)


def test_layout_needs_its_problem_for_pin_endpoints() -> None:
    with pytest.raises(TextError):
        parse_text("kl 1\nlayout\nplace a 0,0 r0\nwire n : a.y E2 -> @3,0\n")
    layout = parse_text(
        "kl 1\nlayout\nwire n carrier=wire layer=ground : cells 1,0 2,0 -> @3,0\n"
    ).layout
    assert isinstance(layout, Layout) and layout.wires["n"].segments[0].cells == (
        (1, 0),
        (2, 0),
        (3, 0),
    )
    assert isinstance(
        parse_text("kl 1\nlib G 1x1 { y out wire E0 }\ncell a G\n").netlist, Netlist
    )


def test_lists_of_one_and_none_read_back_as_lists() -> None:
    from kohakulayout.ir import Fabric, Footprint, Netlist, Problem, Region
    from kohakulayout.ir.text import parse_text

    fabric = Fabric(
        width=4,
        height=4,
        regions={
            "build": Region.of(
                "build", frozenset((x, y) for y in range(4) for x in range(4))
            )
        },
        attrs={"x": {"one": ["a"], "none": [], "two": [1, 2]}},
    )
    problem = Problem(
        physics="null@0",
        fabric=fabric,
        netlist=Netlist(
            pack="null", library={"a": Footprint(id="a", width=1, height=1)}
        ),
        params={"one": [3], "none": [], "flag": True},
    )
    text = problem.text()
    again = parse_text(text).problem
    assert again.fabric.attrs["x"] == {"one": ["a"], "none": [], "two": [1, 2]}
    assert again.params == {"one": [3], "none": [], "flag": True}
    assert again.digest() == problem.digest()
