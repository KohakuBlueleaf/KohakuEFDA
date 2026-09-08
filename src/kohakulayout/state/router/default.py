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

    def __init__(
        self, ripup: int = 3, max_rips: int = 12, rounds: int = 3, **costs: Any
    ) -> None:
        self.ripup = ripup
        self.rounds = rounds
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
        """Plan, rip, commit and re-route the displaced; at the top a displaced net that cannot return protects itself and the round repeats."""
        net = world.netlist.nets[net_id]
        blocked: frozenset[str] = frozenset()
        last: Refusal | None = None
        for _ in range(self.rounds if depth == 0 else 1):
            allow_rip = depth < self.ripup and self._rips_left > 0
            plan = grow(
                world,
                net,
                self.search(world, net, allow_rip, protected | blocked | {net_id}),
            )
            if isinstance(plan, Refusal):
                return plan if last is None else last
            mark = world.mark()
            self._rips_left -= len(plan.rips)
            for victim in sorted(plan.rips):
                for segment in plan.segments:
                    for cell in segment.cells:
                        self.history[(segment.layer, cell)] = (
                            self.history.get((segment.layer, cell), 0) + 1
                        )
                world.unroute(victim)
            refusal = self.commit(
                world, net, plan, allow_rip, protected | blocked | {net_id}
            )
            if refusal is not None:
                return refusal
            failed = None
            for victim in sorted(plan.rips):
                again = self._route(world, victim, depth + 1, protected | {net_id})
                if again is not None:
                    failed = victim
                    last = refuse(
                        net_id,
                        f"displaced {victim}, which could not be re-routed: {again.detail}",
                    )
                    break
            if failed is None:
                return None
            world.rollback_to(mark)
            blocked = blocked | {failed}
        return last

    def commit(
        self,
        world: Any,
        net: Any,
        plan: Plan,
        allow_rip: bool = False,
        protected: frozenset[str] = frozenset(),
    ) -> Refusal | None:
        """Place the plan's units and the wire; a wire under a unit is ripped and joins the victims when ripping is allowed."""
        makers = (
            lambda: crossings(world, net, plan.crossings),
            lambda: junctions(world, net, plan.junctions),
            lambda: repeaters(world, net, plan.segments),
        )
        mark = world.mark()
        while True:
            unit_ids: list[str] = []
            failed: Refusal | None = None
            for make in makers:
                placed = make()
                if isinstance(placed, Refusal):
                    failed = placed
                    break
                unit_ids.extend(placed)
            if failed is None:
                break
            victim = self.wire_under(failed)
            if (
                victim is None
                or not allow_rip
                or self._rips_left <= 0
                or victim in protected
                or victim in plan.rips
            ):
                return failed
            world.rollback_to(mark)
            world.unroute(victim)
            plan.rips.add(victim)
            self._rips_left -= 1
            mark = world.mark()
        world.set_wire(
            Wire(net=net.id, segments=tuple(plan.segments), units=tuple(unit_ids))
        )
        return None

    @staticmethod
    def wire_under(refusal: Refusal) -> str | None:
        """The net whose wire blocks a unit, from the refusal the world attached."""
        holder = refusal.attrs.get("kl", {}).get("holder", "")
        return holder[5:] if holder.startswith("wire:") else None

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
