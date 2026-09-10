"""One workflow per method: the gates problem placed and routed, graded, through the API and the CLI."""

from importlib.resources import files
from pathlib import Path

from typer.testing import CliRunner

from kohakulayout.cli import app
from kohakulayout.cli.io import load_all
from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Layout, Netlist, parse_text, write
from kohakulayout.solvers import get
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.gates import (
    from_expressions,
    problem,
    random_circuit,
)


def fixture_netlist() -> Netlist:
    return Netlist.parse(
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/and_or_not.kl")
        .read_text()
    )


class TestGatesRouting:
    def test_inorder_with_router_completes_and_grades(self) -> None:
        prob = problem(fixture_netlist(), width=24, height=12)
        check = StateCheck()
        ctx = Context(prob, checker=check, router="default")
        assert get("inorder").run(ctx) == "complete"
        assessment = ctx.assess()
        assert assessment.complete and assessment.valid
        assert (
            assessment.metrics["unrouted"] == 0 and assessment.metrics["wire_cells"] > 0
        )
        assert (
            assessment.metrics["extent_w"] <= 24
            and assessment.metrics["extent_h"] <= 12
        )
        layout = ctx.layout()
        assert layout.check_against(prob.netlist, prob.fabric) == []
        text = write(layout, prob)
        assert (
            parse_text(text, context=parse_text(prob.text())).pick(Layout).digest()
            == layout.digest()
        )
        assert check.failures == []

    def test_seed_reproduces_a_routed_random_circuit(self) -> None:
        netlist = random_circuit(4, inputs=3, gates=6)
        digests = set()
        for _ in range(2):
            ctx = Context(
                problem(netlist, width=40, height=20),
                seed=3,
                router="default",
                budget=Budget(units=3000),
            )
            check = StateCheck().mount(ctx.world)
            assert get("baseline").run(ctx) == "complete"
            assert check.failures == []
            digests.add(ctx.world.digest())
        assert len(digests) == 1

    def test_kl_route_writes_a_routed_layout(self, tmp_path: Path) -> None:
        prob = problem(
            from_expressions(["s = a ^ b", "c = a & b"]), width=32, height=16
        )
        placed = Context(prob, router="default")
        assert get("inorder").run(placed) == "complete"
        bare = placed.layout().model_copy(update={"wires": {}, "units": {}})
        problem_path, layout_path, out_path = (
            tmp_path / "p.kl",
            tmp_path / "l.kl",
            tmp_path / "routed.kl",
        )
        problem_path.write_text(prob.text())
        layout_path.write_text(write(bare, prob))
        result = CliRunner().invoke(
            app, ["route", str(problem_path), str(layout_path), "--out", str(out_path)]
        )
        assert result.exit_code == 0, result.output
        routed = load_all([problem_path, out_path]).layout
        assert set(routed.wires) == set(prob.netlist.nets)
        assert routed.check_against(prob.netlist, prob.fabric) == []
