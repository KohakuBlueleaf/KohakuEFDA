"""Problem in, layout and assessment out, through the passes."""

import pytest

from kohakulayout.engine import Budget
from kohakulayout.errors import IRError
from kohakulayout.ir import Cell
from kohakulayout.pipeline import PASSES, PassManager, solve
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.gates import from_expressions, problem


def test_solve_returns_a_graded_answer() -> None:
    result = solve(
        problem(from_expressions("y = a & b | ~c"), width=24, height=12),
        checker=StateCheck(),
        budget=Budget(units=800),
        seed=1,
    )
    assert result.outcome == "complete" and result.assessment.valid
    assert (
        result.layout.check_against(
            result.context.problem.netlist, result.context.problem.fabric
        )
        == []
    )
    assert (
        result.attempts > 0 and result.events is not None and result.events.of("frame")
    )
    assert result.assessment.layout == result.layout.digest()


def test_passes_run_in_order_and_verify() -> None:
    manager = PassManager(("flatten", "check"))
    prob = manager.run(problem(from_expressions("y = a")))
    assert manager.applied == ["flatten", "check"] and prob.netlist.is_flat
    broken = problem(from_expressions("y = a"))
    broken = broken.model_copy(
        update={
            "netlist": broken.netlist.model_copy(
                update={
                    "cells": {
                        **broken.netlist.cells,
                        "bad": Cell(id="bad", footprint="NOPE"),
                    }
                }
            )
        }
    )
    with pytest.raises(IRError):
        PassManager().run(broken)
    PASSES["noop"] = lambda p: p
    assert PassManager(("noop",)).run(prob).digest() == prob.digest()
    del PASSES["noop"]
