"""The execution slot: gather tasks in process, or across worker processes when asked for."""

from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from kohakulayout.errors import NotAvailable

Task = Callable[[], Any] | tuple[Callable[..., Any], tuple[Any, ...]]


def _call(task: Task) -> Any:
    if isinstance(task, tuple):
        fn, args = task
        return fn(*args)
    return task()


class InProcess:
    id = "inprocess"
    workers = 1

    def gather(self, tasks: Iterable[Task]) -> list[Any]:
        return [_call(t) for t in tasks]


class ProcessPool:
    """Tasks as ``(function, args)`` with picklable parts; a pool that cannot start is a configuration answer."""

    id = "process"

    def __init__(self, workers: int = 2) -> None:
        self.workers = max(1, workers)

    def gather(self, tasks: Iterable[Task]) -> list[Any]:
        items = list(tasks)
        if not items:
            return []
        try:
            with ProcessPoolExecutor(max_workers=self.workers) as pool:
                return list(pool.map(_call, items))
        except (OSError, RuntimeError) as exc:
            raise NotAvailable(
                f"worker processes are not available ({exc}); use workers=1 to run in process"
            ) from exc


def make_execution(workers: int = 1) -> Any:
    return InProcess() if workers <= 1 else ProcessPool(workers)


__all__ = ["InProcess", "ProcessPool", "Task", "make_execution"]
