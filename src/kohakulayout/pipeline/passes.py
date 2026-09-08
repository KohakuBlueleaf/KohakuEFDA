"""The pass manager: ordered passes over a problem, each followed by a verify."""

from collections.abc import Callable

from kohakulayout.ir import Problem

Pass = Callable[[Problem], Problem]


def flatten(problem: Problem) -> Problem:
    return problem.model_copy(update={"netlist": problem.netlist.flatten()})


def check(problem: Problem) -> Problem:
    problem.verify()
    return problem


PASSES: dict[str, Pass] = {"flatten": flatten, "check": check}
DEFAULT_PASSES: tuple[str, ...] = ("check",)


class PassManager:
    def __init__(self, passes: tuple[str | Pass, ...] = DEFAULT_PASSES) -> None:
        self.passes: list[tuple[str, Pass]] = []
        for item in passes:
            if isinstance(item, str):
                self.passes.append((item, PASSES[item]))
            else:
                self.passes.append((getattr(item, "__name__", "pass"), item))
        self.applied: list[str] = []

    def run(self, problem: Problem) -> Problem:
        """Every pass in order; the problem verifies after each one."""
        for name, fn in self.passes:
            problem = fn(problem)
            problem.verify()
            self.applied.append(name)
        return problem

    def register(self, name: str, fn: Pass) -> None:
        PASSES[name] = fn
        self.passes.append((name, fn))


__all__ = ["DEFAULT_PASSES", "PASSES", "Pass", "PassManager", "check", "flatten"]
