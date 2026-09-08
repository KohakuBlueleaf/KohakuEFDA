"""The evaluator on a long chain with a recycle every few cells: rounds and microseconds per net.

Prints ``metric <name> <value>`` lines for the ledger.
"""

import statistics
import time
from fractions import Fraction

from kohakulayout.flow import evaluate
from kohakulayout.ir import Netlist
from kohakulayout.physics import DefaultFlow
from kohakulayout.templates.physics.gates import LIBRARY
from kohakulayout.utils import cell, chain

CELLS = 200
REPEATS = 5


class PassThrough(DefaultFlow):
    def transfer(self, cell, inputs):
        if cell.footprint == "BUF":
            return {"y": inputs["a"]}
        return None


def build() -> Netlist:
    cells = {
        "i": cell("i", "IN"),
        **{f"b{k}": cell(f"b{k}", "BUF") for k in range(CELLS)},
    }
    nl = Netlist(pack="gates", library=dict(LIBRARY), cells=cells)
    return chain(nl, ["i", *[f"b{k}" for k in range(CELLS)]], "wire", Fraction(30))


def main() -> None:
    nl = build()
    times: list[float] = []
    rounds = 0
    for _ in range(REPEATS):
        start = time.perf_counter()
        result = evaluate(nl, PassThrough())
        times.append((time.perf_counter() - start) / len(nl.nets) * 1e6)
        rounds = result.rounds
    print(f"metric flow_nets {len(nl.nets)}")
    print(f"metric flow_rounds {rounds}")
    print(f"metric flow_per_net_us {statistics.median(times):.1f}")


if __name__ == "__main__":
    main()
