"""The synth: the basic scenario's netlist as a framework problem, and the same problem from the fixture."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.layout.stages import netlist_stage, plan_stage
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.physics.facts import lane_facts, rate_of
from kohakuefda.synth import kl_id, problem_of, project_pin_id
from kohakuefda.synth.problem import assign, components, constraint_kind, lanes_of
from kohakulayout.ir import Problem
from kohakulayout.ir.text import parse_text

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


@pytest.fixture(scope="module")
def netlist(dataset: Dataset):
    scenario = Scenario.from_toml(FIXTURES / "scenario_basic.toml")
    plan = plan_stage(dataset, scenario)
    return netlist_stage(dataset, scenario, plan)


@pytest.fixture(scope="module")
def problem(dataset: Dataset, netlist) -> Problem:
    return problem_of(dataset, netlist)


def test_the_problem_checks_clean(problem: Problem, netlist) -> None:
    assert problem.check() == []
    assert problem.physics == "endfield@1"
    assert set(problem.netlist.cells) == {c.id for c in netlist.cells}
    for cell in netlist.cells:
        kl = problem.netlist.cells[cell.id]
        assert kl.footprint == cell.machine_id
        assert [p.id for p in kl.pins] == [kl_id(p.id) for p in cell.pins]
        assert all(p.ports for p in kl.pins)
        assert kl.constraint.kind == constraint_kind(cell) and kl.group == cell.group
        assert all(
            project_pin_id(p.id) == q.id
            for p, q in zip(kl.pins, cell.pins, strict=True)
        )


def test_pins_keep_their_default_port_and_alternatives(
    problem: Problem, netlist
) -> None:
    for cell in netlist.cells:
        fp = problem.netlist.library[cell.machine_id]
        for pin, kl in zip(cell.pins, problem.netlist.cells[cell.id].pins, strict=True):
            first = fp.port(kl.ports[0])
            assert first.direction == pin.direction and first.carrier == pin.kind
            if cell.machine_id != "entry":
                assert first.side == pin.edge.value
                assert len(kl.ports) >= len({r.index for r in pin.alternatives})


def test_nets_carry_every_lane_of_the_plan(problem: Problem, netlist) -> None:
    for spec in netlist.nets:
        lanes = lanes_of(spec)
        mine = [
            n
            for n in problem.netlist.nets.values()
            if n.attrs["endfield"]["net"] == spec.id
        ]
        assert len(mine) == len(components(lanes))
        carried = [rate for net in mine for _, _, rate in lane_facts(net)]
        assert sum(carried, Fraction(0)) == sum(
            (rate for _, _, rate in lanes), Fraction(0)
        )
        for net in mine:
            assert net.carrier == spec.kind
            assert net.sources and net.sinks
            capacity = problem.fabric.carriers[net.carrier].capacity
            assert net.rate <= capacity
            assert net.rate == min(rate_of(net.attrs["endfield"]["rate"]), capacity)


def test_best_fit_pairing_matches_the_router() -> None:
    sources = [(("a", "o"), Fraction(30)), (("b", "o"), Fraction(20))]
    sinks = [(("x", "i"), Fraction(20)), (("y", "i"), Fraction(30))]
    assert assign(sources, sinks) == [
        (("a", "o"), ("y", "i"), Fraction(30)),
        (("b", "o"), ("x", "i"), Fraction(20)),
    ]
    split = assign(
        [(("a", "o"), Fraction(10)), (("b", "o"), Fraction(10))],
        [(("x", "i"), Fraction(15))],
    )
    assert [(s, r) for s, _, r in split] == [
        (("a", "o"), Fraction(10)),
        (("b", "o"), Fraction(5)),
    ]
    assert len(components(split)) == 1


def test_powered_machines_need_power_and_groups_are_kept(
    problem: Problem, netlist
) -> None:
    kl = problem.netlist
    for cell in netlist.cells:
        needs = kl.cells[cell.id].needs
        if cell.kind == "recipe":
            assert needs == ("power",)
        if cell.kind in ("entry", "core"):
            assert needs == ()
    for name, group in kl.groups.items():
        assert all(kl.cells[m].group == name for m in group.members)
    assert problem.fabric.regions["area"].cells() and "build" in problem.fabric.regions
    ring = problem.params["ring"]
    assert problem.fabric.width == problem.params["square"][0] + 2 * ring


def test_the_text_form_round_trips(problem: Problem) -> None:
    doc = parse_text(problem.text())
    assert doc.problem.digest() == problem.digest()


def test_the_fixture_is_the_synth_output(problem: Problem) -> None:
    path = FIXTURES / "endfield_basic.kl"
    assert path.exists(), "write the fixture with scripts/dev/endfield_fixture.py"
    doc = parse_text(path.read_text(encoding="utf-8"))
    assert doc.problem.digest() == problem.digest()
