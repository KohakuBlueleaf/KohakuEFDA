"""The gates instance through the in-order solver without a router: placement and assessment cost per cell.

Prints ``metric <name> <value>`` lines for the ledger. Times are microseconds per cell.
"""

import statistics
import time

from kohakulayout.engine import Context
from kohakulayout.solvers import get
from kohakulayout.templates.physics.gates import problem, random_circuit

SEED = 11
GATES = 40
INPUTS = 6
REPEATS = 5


def main() -> None:
    netlist = random_circuit(SEED, inputs=INPUTS, gates=GATES)
    place_us: list[float] = []
    assess_us: list[float] = []
    missing = 0
    for _ in range(REPEATS):
        ctx = Context(problem(netlist, width=96, height=48), seed=SEED, router=None)
        start = time.perf_counter()
        get("inorder").run(ctx)
        place_us.append((time.perf_counter() - start) / len(netlist.cells) * 1e6)
        start = time.perf_counter()
        assessment = ctx.assess()
        assess_us.append((time.perf_counter() - start) / len(netlist.cells) * 1e6)
        missing = assessment.metrics["missing"]
    print(f"metric gates_cells {len(netlist.cells)}")
    print(f"metric gates_missing {missing}")
    print(f"metric gates_inorder_place_us {statistics.median(place_us):.1f}")
    print(f"metric gates_assess_us {statistics.median(assess_us):.1f}")


if __name__ == "__main__":
    main()
