"""Level 3 for the in-order solver on the null and gates toys."""

from importlib.resources import files

from kohakulayout.ir import Netlist
from kohakulayout.solvers import level3
from kohakulayout.templates.physics.gates import problem as gates_problem
from kohakulayout.templates.physics.null import problem as null_problem


def gates_toy():
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/and_or_not.kl")
        .read_text()
    )
    return gates_problem(Netlist.parse(text), width=24, height=12)


TOYS = {"null": lambda: null_problem(width=12, height=12, taps=3), "gates": gates_toy}


def test_inorder_passes_level3() -> None:
    report = level3("inorder", TOYS)
    assert report.failures == [], report.failures
    assert len(report.checks) >= 20
