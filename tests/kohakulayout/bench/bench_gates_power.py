"""The power variant against the plain gates pack through in-order: what the field stage costs per cell.

Prints ``metric <name> <value>`` lines for the ledger.
"""

import statistics
import time
from importlib.resources import files

from kohakulayout.engine import Budget
from kohakulayout.ir import Netlist
from kohakulayout.pipeline import solve
from kohakulayout.templates.physics.gates import problem

REPEATS = 5


def main() -> None:
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/and_or_not.kl")
        .read_text()
    )
    netlist = Netlist.parse(text)
    for name, power in (("plain", False), ("power", True)):
        times: list[float] = []
        emitters = 0
        for _ in range(REPEATS):
            start = time.perf_counter()
            result = solve(
                problem(netlist, power=power, width=24, height=12),
                seed=1,
                budget=Budget(units=4000),
            )
            times.append((time.perf_counter() - start) / len(netlist.cells) * 1e6)
            emitters = result.assessment.metrics.get("emitters", 0)
            assert result.outcome == "complete"
        print(f"metric gates_{name}_inorder_per_cell_us {statistics.median(times):.1f}")
        print(f"metric gates_{name}_emitters {emitters}")


if __name__ == "__main__":
    main()
