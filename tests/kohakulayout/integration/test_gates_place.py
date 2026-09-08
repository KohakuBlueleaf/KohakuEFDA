"""One workflow per method: the gates problem from synth to a text assessment, and back through the IR."""

from kohakulayout.engine import Context
from kohakulayout.ir import Assessment, Layout, Problem, parse_text
from kohakulayout.solvers import get
from kohakulayout.state import StateCheck, World
from kohakulayout.templates.physics.gates import GatesPhysics, from_expressions, problem
from kohakulayout.verify import report


class TestGatesPlacement:
    def test_synth_place_assess_round_trip(self) -> None:
        netlist = from_expressions(["s = a ^ b", "c = a & b", "z = ~(s | c)"])
        prob = problem(netlist, width=32, height=16)
        prob.verify()
        text = prob.text()
        assert parse_text(text).pick(Problem).digest() == prob.digest()

        ctx = Context(prob, checker=StateCheck(), router=None)
        outcome = get("inorder").run(ctx)
        assert outcome == "incomplete"
        layout = ctx.layout()
        assert Layout.parse(layout.text()).digest() == layout.digest()
        assessment = ctx.assess()
        assert Assessment.parse(assessment.text()).digest() == assessment.digest()
        assert assessment.metrics["placed"] == len(netlist.cells)
        assert "unrouted" in report(assessment)

        again = World(prob, GatesPhysics())
        again.load(layout)
        assert again.digest() == ctx.world.digest()
        assert layout.check_against(netlist, prob.fabric) == []
