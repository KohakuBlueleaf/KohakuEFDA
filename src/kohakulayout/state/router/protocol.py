"""The router slot: the protocol, terminals, costs, the refusal shape and the registry."""

from typing import Any, Protocol, runtime_checkable

from kohakulayout.errors import StateError
from kohakulayout.ir import Model, PinRef, Refusal
from kohakulayout.ir.geometry import XY


class Terminal(Model):
    """Where a net touches a pin: the attach cell on the carrier's layer; ``ref`` is None for an edge."""

    ref: PinRef | None = None
    cell: XY
    layer: str
    carrier: str
    direction: str = "in"


class Costs(Model):
    step: int = 1
    turn: int = 1
    crossing: int = 6
    share: int = 0
    corridor: int = 0
    ripup: int = 40
    max_steps: int = 200_000


@runtime_checkable
class Router(Protocol):
    id: str

    def route(self, world: Any, net_id: str) -> Refusal | None: ...
    def unroute(self, world: Any, net_id: str) -> None: ...
    def cost(self, world: Any, net_id: str) -> int | None: ...
    def forget(self) -> None: ...


ROUTERS: dict[str, type] = {}


def register(router: type) -> type:
    ROUTERS[router.id] = router
    return router


def make_router(name: str, **params: Any) -> Any:
    cls = ROUTERS.get(name)
    if cls is None:
        raise StateError(f"no router {name!r}; known: {sorted(ROUTERS)}")
    return cls(**params)


def refuse(net_id: str, detail: str) -> Refusal:
    return Refusal(stage="route", subject=f"net:{net_id}", detail=detail)


def terminals(world: Any, net: Any) -> tuple[Terminal, ...] | Refusal:
    """Every pin's attach cell, sources first; a refusal when a pin's cell is not placed."""
    layer = world.carrier_layer(net.carrier)
    out: list[Terminal] = []
    for direction, refs in (("out", net.sources), ("in", net.sinks)):
        for ref in refs:
            cell = world.attach_cell(ref.cell, ref.pin)
            if cell is None:
                return refuse(net.id, f"pin {ref} is not placed")
            out.append(
                Terminal(
                    ref=ref,
                    cell=cell,
                    layer=layer,
                    carrier=net.carrier,
                    direction=direction,
                )
            )
    return tuple(out)


__all__ = [
    "ROUTERS",
    "Costs",
    "Router",
    "Terminal",
    "make_router",
    "refuse",
    "register",
    "terminals",
]
