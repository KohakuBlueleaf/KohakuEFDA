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
    options: tuple[tuple[str, XY], ...] = ()
    bound: bool = True


class Costs(Model):
    step: int = 1
    turn: int = 1
    crossing: int = 6
    share: int = 0
    corridor: int = 0
    ripup: int = 40
    displace: int = 4
    max_steps: int = 200_000
    detour: float = 0.0
    slack: float = 0.0


@runtime_checkable
class Router(Protocol):
    """What the world asks of a router: ``route``; one may also carry ``order(world, cell_id, pending, grown)``, the order the nets one placement touches route in, the widest span first without it."""

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
    """Every placed pin with the ports it may still take, sources first; a refusal when no placed pin feeds the net or none takes from it, or a placed pin has no open port."""
    layer = world.carrier_layer(net.carrier)
    out: list[Terminal] = []
    for direction, refs in (("out", net.sources), ("in", net.sinks)):
        for ref in refs:
            if ref.cell not in world.placements:
                continue
            options = world.open_ports(ref.cell, ref.pin)
            if not options:
                return refuse(net.id, f"pin {ref} has no open port")
            pin = world.netlist.pin(ref)
            out.append(
                Terminal(
                    ref=ref,
                    cell=options[0][1],
                    layer=layer,
                    carrier=net.carrier,
                    direction=direction,
                    options=options,
                    bound=pin is None or len(pin.ports) <= 1,
                )
            )
    fed = net.outside is not None or any(t.direction == "out" for t in out)
    if not fed:
        return refuse(net.id, "no placed source feeds it yet")
    if not any(t.direction == "in" for t in out):
        return refuse(net.id, "no placed sink takes from it yet")
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
