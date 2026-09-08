"""Every shipped solver on the and-or-not gates toy: outcome, area and wall time.

Prints ``metric <name> <value>`` lines for the ledger.
"""

import time
from importlib.resources import files

from kohakulayout.engine import Budget
from kohakulayout.ir import Netlist
from kohakulayout.pipeline import solve
from kohakulayout.templates.physics.gates import problem

SOLVERS = ("inorder", "baseline", "regional", "climb", "anneal")
UNITS = 4000
SEED = 7


def main() -> None:
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/and_or_not.kl")
        .read_text()
    )
    toy = problem(Netlist.parse(text), width=24, height=12)
    for solver in SOLVERS:
        start = time.perf_counter()
        result = solve(toy, solver=solver, seed=SEED, budget=Budget(units=UNITS))
        elapsed = time.perf_counter() - start
        print(f"metric {solver}_complete {int(result.outcome == 'complete')}")
        print(f"metric {solver}_area {result.assessment.metrics['area']}")
        print(f"metric {solver}_attempts {result.attempts}")
        print(f"metric {solver}_seconds {elapsed:.2f}")


if __name__ == "__main__":
    main()
