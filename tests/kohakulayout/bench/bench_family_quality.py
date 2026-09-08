"""The coordinate family on a seeded set of random gates circuits: completion counts and areas.

Prints ``metric <name> <value>`` lines for the ledger. Completion counts are exact; areas are medians,
over every completed circuit and over the circuits in-order completes (``_shared``), and per seed.
"""

import statistics
import sys
import time

from kohakulayout.engine import Budget
from kohakulayout.pipeline import solve
from kohakulayout.templates.physics.gates import problem, random_circuit

SEEDS = tuple(range(1, 9))
INPUTS = 4
GATES = 8
BOARD = (48, 24)
UNITS = 4000
SOLVERS = {
    "inorder": {},
    "baseline": {"shrink_rounds": 30},
    "regional": {"attempts": 32, "shrink_rounds": 30},
    "climb": {"improvement_steps": 300, "until_budget": False},
    "anneal": {"improvement_steps": 300, "until_budget": False},
}


def main() -> None:
    only = sys.argv[1:] or list(SOLVERS)
    shared: dict[int, int] = {}
    for solver in ["inorder", *(s for s in only if s != "inorder")]:
        params = SOLVERS[solver]
        complete = 0
        areas: list[int] = []
        by_seed: dict[int, int] = {}
        start = time.perf_counter()
        for seed in SEEDS:
            netlist = random_circuit(seed, inputs=INPUTS, gates=GATES)
            result = solve(
                problem(netlist, width=BOARD[0], height=BOARD[1]),
                solver=solver,
                seed=seed,
                budget=Budget(units=UNITS),
                params=params,
            )
            if result.outcome == "complete":
                complete += 1
                areas.append(int(result.assessment.metrics["area"]))
                by_seed[seed] = areas[-1]
        elapsed = time.perf_counter() - start
        if solver == "inorder":
            shared.update(by_seed)
        common = [a for seed, a in by_seed.items() if seed in shared]
        print(f"metric quality_{solver}_complete {complete}")
        print(
            f"metric quality_{solver}_area {statistics.median(areas) if areas else 0}"
        )
        print(
            f"metric quality_{solver}_area_shared {statistics.median(common) if common else 0}"
        )
        for seed in SEEDS:
            print(f"metric quality_{solver}_area_s{seed} {by_seed.get(seed, 0)}")
        print(f"metric quality_{solver}_seconds {elapsed:.1f}")


if __name__ == "__main__":
    main()
