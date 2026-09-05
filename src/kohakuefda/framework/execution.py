"""Bounded isolated job execution; callers own task generation and result selection."""

import logging
import multiprocessing
import time
import traceback
from collections.abc import Callable
from multiprocessing.connection import wait

from kohakuefda.framework.control import Budget, FrameworkError

POLL_SECONDS = 0.1
JOIN_SECONDS = 0.2
log = logging.getLogger(__name__)


def _execute(connection, function, arguments) -> None:
    try:
        connection.send((True, function(*arguments)))
    except Exception:
        log.exception("isolated solver job failed")
        connection.send((False, traceback.format_exc()))
    finally:
        connection.close()


def gather(
    function: Callable,
    jobs: tuple[tuple, ...],
    workers: int,
    budget: Budget,
    observe=None,
) -> list:
    """Execute a batch in input order; terminate outstanding children on every failed exit."""
    if workers < 1:
        raise ValueError("workers must be positive")
    context = multiprocessing.get_context("spawn")
    pending, processes, results = {}, [], {}
    next_job = 0
    try:
        while next_job < len(jobs) or pending:
            budget.check()
            while next_job < len(jobs) and len(pending) < workers:
                receive, send = context.Pipe(duplex=False)
                process = context.Process(
                    target=_execute, args=(send, function, jobs[next_job])
                )
                process.start()
                send.close()
                processes.append(process)
                pending[receive] = (next_job, process, time.monotonic())
                next_job += 1
            for connection in wait(list(pending), timeout=POLL_SECONDS):
                index, process, started = pending.pop(connection)
                try:
                    ok, value = connection.recv()
                except EOFError as error:
                    raise FrameworkError(
                        f"worker {index} exited without a result"
                    ) from error
                finally:
                    connection.close()
                process.join(JOIN_SECONDS)
                if not ok:
                    raise FrameworkError(f"worker {index}: {value}")
                results[index] = value
                if observe:
                    observe(
                        "worker",
                        {"task": index, "completed": len(results), "total": len(jobs)},
                        time.monotonic() - started,
                    )
        return [results[i] for i in range(len(jobs))]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(JOIN_SECONDS)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        for connection in pending:
            connection.close()
