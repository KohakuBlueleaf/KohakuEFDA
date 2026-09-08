"""The floorplan solver on the bank fixture: outcome, area and wall time.

Prints ``metric <name> <value>`` lines for the ledger.
"""

import time
from importlib.resources import files

from kohakulayout.engine import Budget
from kohakulayout.ir import Netlist
from kohakulayout.pipeline import solve
from kohakulayout.templates.physics.gates import problem


def main() -> None:
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/bank.kl")
        .read_text()
    )
    toy = problem(Netlist.parse(text), width=40, height=12)
    start = time.perf_counter()
    result = solve(
        toy,
        solver="floorplan",
        seed=3,
        budget=Budget(units=6000),
        params={"steps": 40, "until_budget": False},
    )
    elapsed = time.perf_counter() - start
    print(f"metric floorplan_complete {int(result.outcome == 'complete')}")
    print(f"metric floorplan_area {result.assessment.metrics['area']}")
    print(f"metric floorplan_attempts {result.attempts}")
    print(f"metric floorplan_seconds {elapsed:.2f}")


if __name__ == "__main__":
    main()
