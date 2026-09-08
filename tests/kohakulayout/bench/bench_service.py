"""The service's own cost: submit-to-done through the local service against the pipeline, and the process spawn.

Prints ``metric <name> <value>`` lines for the ledger. Times are milliseconds.
"""

import statistics
import tempfile
import time
from pathlib import Path

from kohakulayout.engine import Budget
from kohakulayout.pipeline import solve
from kohakulayout.service import LocalService, ProcessService, Request
from kohakulayout.templates.physics.gates import from_expressions, problem

REPEATS = 5


def main() -> None:
    prob = problem(from_expressions("y = a & b | ~c"), width=24, height=12)
    request = Request(solver="inorder", seed=1, units=800)
    direct: list[float] = []
    local: list[float] = []
    spawned: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for _ in range(REPEATS):
            start = time.perf_counter()
            solve(prob, seed=1, budget=Budget(units=800))
            direct.append((time.perf_counter() - start) * 1e3)
            service = LocalService(root / "local")
            start = time.perf_counter()
            run = service.submit(prob, request)
            local.append((time.perf_counter() - start) * 1e3)
            assert service.status(run).state == "done"
            process = ProcessService(root / "process")
            start = time.perf_counter()
            run = process.submit(prob, request)
            process.wait(run, timeout=120)
            spawned.append((time.perf_counter() - start) * 1e3)
            process.close()
    print(f"metric service_direct_ms {statistics.median(direct):.1f}")
    print(f"metric service_local_ms {statistics.median(local):.1f}")
    print(f"metric service_process_ms {statistics.median(spawned):.1f}")


if __name__ == "__main__":
    main()
