"""The solver protocol: a typed parameter schema, a run over a context, and an outcome."""

from typing import Any, Literal, Protocol, runtime_checkable

from kohakulayout.ir import Model

Outcome = Literal["complete", "incomplete", "failed"]
ParamType = Literal["int", "float", "fraction", "bool", "choice", "seconds"]


class Param(Model):
    name: str
    type: ParamType
    default: Any = None
    choices: tuple[str, ...] = ()
    doc: str = ""


@runtime_checkable
class Solver(Protocol):
    id: str
    params: tuple[Param, ...]

    def run(self, ctx: Any, **params: Any) -> Outcome: ...


__all__ = ["Outcome", "Param", "ParamType", "Solver"]
