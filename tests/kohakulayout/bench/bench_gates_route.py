"""The gates instance placed and routed through in-order and the default router; per-cell and per-net cost.

Prints ``metric <name> <value>`` lines for the ledger. Times are microseconds.
"""

import statistics
import time

from kohakulayout.engine import Context
from kohakulayout.solvers import get
from kohakulayout.templates.physics.gates import problem, random_circuit

SEED = 2
GATES = 12
INPUTS = 4
REPEATS = 5


def main() -> None:
    netlist = random_circuit(SEED, inputs=INPUTS, gates=GATES)
    per_cell: list[float] = []
    per_net: list[float] = []
    complete = 0
    jumpers = 0
    for _ in range(REPEATS):
        ctx = Context(
            problem(netlist, width=64, height=32), seed=SEED, router="default"
        )
        start = time.perf_counter()
        outcome = get("inorder").run(ctx)
        elapsed = time.perf_counter() - start
        per_cell.append(elapsed / len(netlist.cells) * 1e6)
        per_net.append(elapsed / len(netlist.nets) * 1e6)
        complete = int(outcome == "complete")
        jumpers = ctx.assess().metrics["jumpers"]
    print(f"metric gates_route_cells {len(netlist.cells)}")
    print(f"metric gates_route_nets {len(netlist.nets)}")
    print(f"metric gates_route_complete {complete}")
    print(f"metric gates_route_jumpers {jumpers}")
    print(f"metric gates_route_per_cell_us {statistics.median(per_cell):.1f}")
    print(f"metric gates_route_per_net_us {statistics.median(per_net):.1f}")


if __name__ == "__main__":
    main()
