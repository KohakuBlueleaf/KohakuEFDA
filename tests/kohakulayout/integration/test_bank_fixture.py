"""One workflow: the bank fixture parses, flattens and folds by digest, and solves through in-order with the router."""

from importlib.resources import files

from kohakulayout.engine import Budget
from kohakulayout.ir import Netlist, parse_text
from kohakulayout.pipeline import solve
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.gates import problem


class TestBankFixture:
    def test_bank_flattens_folds_and_solves(self) -> None:
        text = (
            files("kohakulayout.templates.physics.gates")
            .joinpath("fixtures/bank.kl")
            .read_text()
        )
        netlist = Netlist.parse(text)
        netlist.verify()
        flat = netlist.flatten()
        assert (
            flat.digest() == netlist.digest()
            and len(flat.cells) == 10
            and len(flat.nets) == 3
        )
        assert netlist.macros["BANK_ROW"].footprint.width == 15
        again = parse_text(netlist.text()).pick(Netlist)
        assert (
            again.digest() == netlist.digest()
            and again.modules.keys() == netlist.modules.keys()
        )
        result = solve(
            problem(netlist, width=40, height=12),
            solver="inorder",
            seed=2,
            budget=Budget(units=4000),
            checker=StateCheck(),
        )
        assert result.outcome == "complete" and result.assessment.valid
        assert set(result.layout.placements) == set(flat.cells)
