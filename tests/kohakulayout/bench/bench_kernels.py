"""The Python kernel against the native one on the same recorded op sequence and the same queries.

Prints ``metric <name> <value>`` lines for the ledger. Times are microseconds per operation.
"""

import statistics
import sys
import time

from kohakulayout._rust import HAS_RUST
from kohakulayout.engine import Budget, Context
from kohakulayout.solvers import get
from kohakulayout.state import World, make_router
from kohakulayout.state.kernel import NativeKernel, PyKernel, RecordingKernel, replay
from kohakulayout.templates.physics.gates import GatesPhysics, problem, random_circuit

REPEATS = 5


def main() -> None:
    if not HAS_RUST:
        print(
            "kohakulayout_rs is not built; run maturin develop in src/kohakulayout-rs",
            file=sys.stderr,
        )
        sys.exit(2)
    prob = problem(random_circuit(2, inputs=4, gates=12), width=64, height=32)
    size = (prob.fabric.width, prob.fabric.height, tuple(prob.fabric.layers))
    recorder = RecordingKernel(PyKernel(*size))
    world = World(prob, GatesPhysics(), kernel=recorder, router=make_router("default"))
    ctx = Context(prob, seed=2, budget=Budget(units=6000))
    ctx.world = world
    get("inorder").run(ctx)
    log = list(recorder.log)
    results: dict[str, list[float]] = {"python": [], "native": []}
    for name, factory in (("python", PyKernel), ("native", NativeKernel)):
        for _ in range(REPEATS):
            kernel = factory(*size)
            start = time.perf_counter()
            replay(log, kernel)
            for _ in range(200):
                kernel.free_for("ground", [(5, 5), (6, 5), (7, 5)])
                kernel.holders_at("ground", (10, 10))
            kernel.extent()
            results[name].append((time.perf_counter() - start) / (len(log) + 401) * 1e6)
    print(f"metric kernel_ops {len(log)}")
    print(f"metric kernel_python_us_per_op {statistics.median(results['python']):.2f}")
    print(f"metric kernel_native_us_per_op {statistics.median(results['native']):.2f}")


if __name__ == "__main__":
    main()
