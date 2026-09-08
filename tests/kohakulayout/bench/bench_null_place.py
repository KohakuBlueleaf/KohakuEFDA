"""The null instance: what a placement, a refusal, a digest and a snapshot cost before any game.

Prints ``metric <name> <value>`` lines for the ledger. Times are microseconds per call.
"""

import statistics
import time

from kohakulayout.physics import get
from kohakulayout.state import World
from kohakulayout.templates.physics.null import problem as null_problem

SIZE = 24
TAPS = 12
REPEATS = 5


def walk(world: World) -> float:
    order, _ = world.netlist.flow_order()
    start = time.perf_counter()
    with world.transaction() as tx:
        for cell_id in order:
            anchor = world.first_open(cell_id)
            assert anchor is not None, cell_id
            assert world.place(cell_id, anchor.x, anchor.y, anchor.rot) is None, cell_id
        tx.commit()
    return (time.perf_counter() - start) / len(order) * 1e6


def refuse(world: World) -> float:
    start = time.perf_counter()
    with world.transaction():
        for _ in range(100):
            assert world.place("c", 0, 0).stage == "overlap"
    return (time.perf_counter() - start) / 100 * 1e6


def digest(world: World) -> float:
    start = time.perf_counter()
    for _ in range(20):
        world.digest()
    return (time.perf_counter() - start) / 20 * 1e6


def snapshot(world: World) -> float:
    start = time.perf_counter()
    for _ in range(20):
        world.restore(world.snapshot())
    return (time.perf_counter() - start) / 20 * 1e6


def main() -> None:
    samples: dict[str, list[float]] = {
        "place": [],
        "refuse": [],
        "digest": [],
        "snapshot": [],
    }
    for _ in range(REPEATS):
        problem = null_problem(width=SIZE, height=SIZE, taps=TAPS)
        world = World(problem, get(problem.physics))
        samples["place"].append(walk(world))
        with world.transaction() as tx:
            world.withdraw("c")
            tx.commit()
        samples["refuse"].append(refuse(world))
        samples["digest"].append(digest(world))
        samples["snapshot"].append(snapshot(world))
    print(f"metric null_cells {2 * TAPS + 2}")
    for name, values in samples.items():
        print(f"metric null_{name}_us {statistics.median(values):.1f}")


if __name__ == "__main__":
    main()
