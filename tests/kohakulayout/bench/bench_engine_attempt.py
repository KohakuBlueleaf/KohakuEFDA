"""What the engine adds to a placement: an attempt through the context against a raw world place.

Prints ``metric <name> <value>`` lines for the ledger. Times are microseconds per call.
"""

import statistics
import time

from kohakulayout.engine import Budget, Context
from kohakulayout.pipeline import solve
from kohakulayout.templates.physics.gates import from_expressions, problem
from kohakulayout.templates.physics.null import problem as null_problem

REPEATS = 5
SIZE = 24
TAPS = 12


def raw(world) -> float:
    order, _ = world.netlist.flow_order()
    start = time.perf_counter()
    with world.transaction() as tx:
        for cell_id in order:
            anchor = world.first_open(cell_id)
            world.place(cell_id, anchor.x, anchor.y, anchor.rot)
        tx.commit()
    return (time.perf_counter() - start) / len(order) * 1e6


def through_engine(ctx: Context) -> float:
    order, _ = ctx.world.netlist.flow_order()
    start = time.perf_counter()
    for cell_id in order:
        anchor = ctx.world.first_open(cell_id)
        ctx.attempt(lambda b, c=cell_id, a=anchor: b.place(c, a))
    return (time.perf_counter() - start) / len(order) * 1e6


def main() -> None:
    raws: list[float] = []
    attempts: list[float] = []
    solves: list[float] = []
    for _ in range(REPEATS):
        raws.append(
            raw(
                Context(
                    null_problem(width=SIZE, height=SIZE, taps=TAPS), router=None
                ).world
            )
        )
        attempts.append(
            through_engine(
                Context(null_problem(width=SIZE, height=SIZE, taps=TAPS), router=None)
            )
        )
        start = time.perf_counter()
        result = solve(
            problem(from_expressions("y = a & b | ~c"), width=24, height=12),
            budget=Budget(units=800),
        )
        solves.append((time.perf_counter() - start) * 1e6)
        assert result.outcome == "complete"
    print(f"metric engine_raw_place_us {statistics.median(raws):.1f}")
    print(f"metric engine_attempt_place_us {statistics.median(attempts):.1f}")
    print(f"metric engine_solve_aon_us {statistics.median(solves):.1f}")


if __name__ == "__main__":
    main()
