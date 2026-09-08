"""The default router: negotiated congestion with rip-up, trees, crossing units, sharing, reservations."""

from typing import Any

from kohakulayout.ir import Refusal, Wire
from kohakulayout.ir.geometry import XY
from kohakulayout.state.router.pathfinder import Search
from kohakulayout.state.router.protocol import Costs, refuse, register
from kohakulayout.state.router.reservations import walls
from kohakulayout.state.router.trees import Plan, grow
from kohakulayout.state.router.units import crossings, junctions, repeaters


@register
class DefaultRouter:
    id = "default"

    def __init__(self, ripup: int = 3, max_rips: int = 12, **costs: Any) -> None:
        self.ripup = ripup
        self.max_rips = max_rips
        self._rips_left = 0
        self.costs = Costs(**costs)
        self.history: dict[tuple[str, XY], int] = {}
        self._walls: dict[tuple[int, str], tuple[Any, frozenset[XY]]] = {}

    def walls_for(self, world: Any, carrier: str) -> frozenset[XY]:
        key = (id(world.fabric), carrier)
        cached = self._walls.get(key)
        if cached is None or cached[0] is not world.fabric:
            cached = (world.fabric, walls(world, carrier))
            self._walls[key] = cached
        return cached[1]

    def search(
        self, world: Any, net: Any, allow_rip: bool, protected: frozenset[str]
    ) -> Search:
        return Search(
            world=world,
            net_id=net.id,
            carrier=net.carrier,
            layer=world.carrier_layer(net.carrier),
            costs=self.costs,
            walls=self.walls_for(world, net.carrier),
            history=self.history,
            allow_rip=allow_rip,
            protected=protected,
        )

    def route(self, world: Any, net_id: str) -> Refusal | None:
        self._rips_left = self.max_rips
        return self._route(world, net_id, 0, frozenset())

    def _route(
        self, world: Any, net_id: str, depth: int, protected: frozenset[str]
    ) -> Refusal | None:
        net = world.netlist.nets[net_id]
        allow_rip = depth < self.ripup and self._rips_left > 0
        plan = grow(
            world, net, self.search(world, net, allow_rip, protected | {net_id})
        )
        if isinstance(plan, Refusal):
            return plan
        self._rips_left -= len(plan.rips)
        for victim in sorted(plan.rips):
            for segment in plan.segments:
                for cell in segment.cells:
                    self.history[(segment.layer, cell)] = (
                        self.history.get((segment.layer, cell), 0) + 1
                    )
            world.unroute(victim)
        refusal = self.commit(world, net, plan)
        if refusal is not None:
            return refusal
        for victim in sorted(plan.rips):
            again = self._route(world, victim, depth + 1, protected | {net_id})
            if again is not None:
                return refuse(
                    net_id,
                    f"displaced {victim}, which could not be re-routed: {again.detail}",
                )
        return None

    def commit(self, world: Any, net: Any, plan: Plan) -> Refusal | None:
        unit_ids: list[str] = []
        for placed in (
            crossings(world, net, plan.crossings),
            junctions(world, net, plan.junctions),
            repeaters(world, net, plan.segments),
        ):
            if isinstance(placed, Refusal):
                return placed
            unit_ids.extend(placed)
        world.set_wire(
            Wire(net=net.id, segments=tuple(plan.segments), units=tuple(unit_ids))
        )
        return None

    def unroute(self, world: Any, net_id: str) -> None:
        world.unroute(net_id)

    def forget(self) -> None:
        """Drop the negotiation history; the world calls this when its state jumps to a snapshot."""
        self.history.clear()

    def cost(self, world: Any, net_id: str) -> int | None:
        net = world.netlist.nets[net_id]
        plan = grow(world, net, self.search(world, net, False, frozenset({net_id})))
        return None if isinstance(plan, Refusal) else plan.cost


__all__ = ["DefaultRouter"]
