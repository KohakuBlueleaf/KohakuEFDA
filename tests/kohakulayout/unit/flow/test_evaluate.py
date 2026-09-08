"""The evaluator: splits, merges, capacity, starvation, and the recycle loop pinned as expected behaviour."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakulayout.errors import KohakuLayoutError
from kohakulayout.flow import (
    CAPACITY,
    EVALUATORS,
    LOOP,
    STARVED,
    UNSTABLE,
    FixedPoint,
    cycles,
    evaluate,
)
from kohakulayout.ir import Carrier, Netlist, Problem, parse_text
from kohakulayout.physics import DefaultFlow


class Recycle(DefaultFlow):
    """The mixer makes what it gets on both inputs, capped at twelve; the stage passes through."""

    evaluates = True

    def __init__(self, cap: int = 12, out_demand: int = 2) -> None:
        self.cap = Fraction(cap)
        self.out_demand = Fraction(out_demand)

    def demand(self, cell, pin):
        return {
            ("mix", "a"): Fraction(10),
            ("mix", "b"): Fraction(2),
            ("out", "a"): self.out_demand,
            ("stage", "a"): Fraction(1),
        }.get((cell.id, pin))

    def transfer(self, cell, inputs):
        if cell.footprint == "MIX":
            return {"y": min(inputs["a"] + inputs["b"], self.cap)}
        if cell.footprint == "PASS":
            return {"y": inputs["a"]}
        return None


@pytest.fixture
def recycle(kl_fixtures: Path) -> Netlist:
    return parse_text((kl_fixtures / "recycle.kl").read_text()).pick(Netlist)


def test_loop_keeps_its_declared_rates(recycle: Netlist) -> None:
    result = evaluate(recycle, Recycle())
    assert result.converged and result.rounds <= 3
    assert cycles(recycle) == ("back", "made") and result.loops == ("back", "made")
    assert result.nets == {
        "feed": Fraction(10),
        "made": Fraction(8),
        "back": Fraction(4),
    }
    assert result.at("mix", "b") == Fraction(2) and result.at("out", "a") == Fraction(2)
    assert [f.rule for f in result.findings] == [LOOP]


def test_a_cell_making_less_pulls_the_loop_down(recycle: Netlist) -> None:
    result = evaluate(recycle, Recycle(cap=6))
    assert result.converged
    assert result.nets["made"] == Fraction(6)
    assert result.at("mix", "y") == Fraction(6) and result.nets["back"] == Fraction(4)
    assert {f.rule for f in result.findings} == {LOOP}


def test_starvation_and_capacity(recycle: Netlist) -> None:
    result = evaluate(recycle, Recycle(out_demand=3))
    rules = [f.rule for f in result.findings]
    assert rules.count(STARVED) == 1 and "out.a" in result.findings[0].subject
    fabric = (
        Problem.parse(
            "physics gates@1\nfabric 8x8 layers=ground\ncarrier wire ground\n"
        ).fabric
        if False
        else None
    )
    capped = recycle.model_copy()
    fabric = type(
        "F",
        (),
        {
            "carriers": {
                "wire": Carrier(id="wire", layer="ground", capacity=Fraction(5))
            }
        },
    )()
    result = evaluate(capped, Recycle(), fabric)
    rules = [f.rule for f in result.findings]
    assert CAPACITY in rules and STARVED in rules
    assert result.nets["feed"] == Fraction(5) and result.at("mix", "a") == Fraction(5)


def test_split_merge_and_the_slot(recycle: Netlist) -> None:
    flow = DefaultFlow()
    assert (
        flow.split(Fraction(9), 3) == (Fraction(3),) * 3
        and flow.split(Fraction(9), 0) == ()
    )
    assert flow.merge((Fraction(6), Fraction(2)), Fraction(4)) == (
        Fraction(3),
        Fraction(1),
    )
    assert (
        flow.demand(None, "a") is None
        and flow.transfer(None, {}) is None
        and not flow.evaluates
    )
    plain = evaluate(recycle, flow)
    assert (
        plain.converged
        and plain.nets["back"] == Fraction(4)
        and [f.rule for f in plain.findings] == [LOOP]
    )
    assert plain.at("out", "a") == Fraction(2)
    assert "fixedpoint" in EVALUATORS and isinstance(
        EVALUATORS["fixedpoint"](), FixedPoint
    )
    with pytest.raises(KohakuLayoutError, match="no flow evaluator"):
        evaluate(recycle, flow, evaluator="nowhere")


def test_unstable_when_rounds_run_out(recycle: Netlist) -> None:
    class Drifting(Recycle):
        def transfer(self, cell, inputs):
            if cell.footprint == "MIX":
                return {"y": inputs["b"] * 2 - Fraction(1, 1000)}
            return super().transfer(cell, inputs)

    result = evaluate(recycle, Drifting(), max_rounds=5)
    assert not result.converged and result.rounds == 5
    assert UNSTABLE in [f.rule for f in result.findings]


def test_runner_includes_flow_findings_when_the_pack_asks(recycle: Netlist) -> None:
    from kohakulayout.engine import Context
    from kohakulayout.templates.physics.gates import GatesPhysics, problem

    physics = GatesPhysics()
    physics.flow = Recycle(out_demand=3)
    prob = problem(recycle, width=16, height=8)
    ctx = Context(prob, physics=physics, router=None)
    rules = {f.rule for f in ctx.assess().findings}
    assert STARVED in rules and LOOP in rules
