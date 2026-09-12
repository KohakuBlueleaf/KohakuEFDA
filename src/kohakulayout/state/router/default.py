"""The default router: negotiated congestion in passes with a rising present cost, trees, crossing units, sharing, reservations."""

from typing import Any

from kohakulayout.ir import Refusal, Wire
from kohakulayout.ir.geometry import XY
from kohakulayout.state.chain import recover
from kohakulayout.state.router.pathfinder import Search
from kohakulayout.state.router.protocol import Costs, refuse, register
from kohakulayout.state.router.reservations import unit_walls, walls
from kohakulayout.state.router.trees import (
    DEFAULT_POLICY,
    Plan,
    TreePolicy,
    grow,
    seed_of,
)
from kohakulayout.state.router.units import crossings, junctions, repeaters


@register
class DefaultRouter:
    id = "default"

    def __init__(
        self, passes: int = 40, growth: float = 1.5, max_rips: int = 400, **costs: Any
    ) -> None:
        self.passes = passes
        self.growth = growth
        self.max_rips = max_rips
        self._rips_left = 0
        self.costs = Costs(**costs)
        self.history: dict[tuple[str, XY], int] = {}
        self._walls: dict[tuple[int, str], tuple[Any, frozenset[XY]]] = {}
        self.policy: TreePolicy = DEFAULT_POLICY

    def plan(self, world: Any, net: Any, search: Search, seed: Any) -> Plan | Refusal:
        """The tree a net will become: the framework's growth under this router's tree policy; an override point."""
        return grow(world, net, search, seed, self.policy)

    def order(
        self, world: Any, cell_id: str, pending: list[str], grown: set[str]
    ) -> list[str]:
        """The order the nets a placement touches route in: the widest span first; a router with a policy of its own overrides it."""
        return sorted(dict.fromkeys(pending), key=world.span, reverse=True)

    def order_data(self, world: Any, net: Any) -> dict[str, Any] | None:
        """The net order as data for the native twin; None when a subclass orders otherwise."""
        if type(self).order is not DefaultRouter.order:
            return None
        return {"kind": "span"}

    def walls_for(self, world: Any, carrier: str) -> frozenset[XY]:
        key = (id(world.fabric), carrier)
        cached = self._walls.get(key)
        if cached is None or cached[0] is not world.fabric:
            cached = (world.fabric, walls(world, carrier))
            self._walls[key] = cached
        return cached[1]

    def unit_walls_for(self, world: Any, carrier: str) -> frozenset[XY]:
        """Where the carrier's own crossing unit may not stand, once per fabric."""
        key = (id(world.fabric), f"units:{carrier}")
        cached = self._walls.get(key)
        if cached is None or cached[0] is not world.fabric:
            unit = world.physics.carriers.crossing(carrier, carrier).unit
            cached = (world.fabric, unit_walls(world, unit))
            self._walls[key] = cached
        return cached[1]

    def search(
        self,
        world: Any,
        net: Any,
        present: int,
        protected: frozenset[str],
        allow_rip: bool = True,
    ) -> Search:
        """The search for one net at this pass's present cost: a displaced cell costs ``present`` times one plus its history, while rips are allowed and left."""
        return Search(
            world=world,
            net_id=net.id,
            carrier=net.carrier,
            layer=world.carrier_layer(net.carrier),
            costs=self.costs.model_copy(update={"ripup": present}),
            walls=self.walls_for(world, net.carrier),
            unit_walls=self.unit_walls_for(world, net.carrier),
            history=self.history,
            allow_rip=allow_rip and self._rips_left > 0,
            protected=protected,
        )

    def route(self, world: Any, net_id: str) -> Refusal | None:
        """Negotiated congestion: route the net at the present cost, ripping what stands in its way; the displaced re-route in the same pass without displacing anyone; every pass raises the present cost until nothing stays displaced; a pass that displaced nothing and still failed, or the last pass, rolls the whole route back. A net that already has a wire keeps its tree and grows to the pins off it."""
        self._rips_left = self.max_rips
        mark = world.mark()
        present = max(1, self.costs.ripup)
        pending = [net_id]
        last: Refusal | None = None
        seeds: dict[str, Any] = {}
        if net_id in world.wires:
            seeds[net_id] = seed_of(world, world.netlist.nets[net_id])
            world.unroute(net_id)
        for _ in range(self.passes):
            queue = list(pending)
            position = 0
            failed: list[str] = []
            contested = False
            while position < len(queue):
                current = queue[position]
                position += 1
                if current in world.wires:
                    continue
                net = world.netlist.nets[current]
                search = self.search(
                    world, net, present, frozenset({current}), current == net_id
                )
                plan = self.plan(world, net, search, seeds.get(current))
                if isinstance(plan, Refusal):
                    failed.append(current)
                    last = plan
                    continue
                self._rips_left -= len(plan.rips)
                contested = contested or bool(plan.rips)
                if plan.rips:
                    self.remember(world, plan)
                for victim in sorted(plan.rips):
                    world.unroute(victim)
                refusal = self.commit(
                    world, net, plan, search.allow_rip, frozenset({current})
                )
                if refusal is not None:
                    failed.append(current)
                    last = refusal
                contested = contested or bool(plan.rips)
                for victim in sorted(plan.rips):
                    if victim not in world.wires and victim not in queue[position:]:
                        queue.append(victim)
            if not failed:
                return None
            if not contested:
                break
            pending = failed
            present = max(present + 1, int(present * self.growth))
        world.rollback_to(mark)
        detail = last.detail if last is not None else ""
        return refuse(net_id, f"not routed: {detail}")

    def remember(self, world: Any, plan: Plan) -> None:
        """Charge history on the plan's cells another wire held, so a contested cell prices higher next time; the world's undo log reverts the charge with a rollback."""
        mine = f"wire:{plan.net_id}"
        for segment in plan.segments:
            for cell in segment.cells:
                holders = world.kernel.holders_at(segment.layer, cell)
                if not any(h.startswith("wire:") and h != mine for h in holders):
                    continue
                key = (segment.layer, cell)
                before = self.history.get(key, 0)
                self.history[key] = before + 1
                world.record(lambda k=key, b=before: self.history.__setitem__(k, b))

    def commit(
        self,
        world: Any,
        net: Any,
        plan: Plan,
        allow_rip: bool = False,
        protected: frozenset[str] = frozenset(),
    ) -> Refusal | None:
        """Place the plan's units and the wire, the field emitters the path displaces removed first and the cover redone after; a wire under a unit is ripped and joins the victims when ripping is allowed."""
        makers = (
            lambda: crossings(world, net, plan.crossings),
            lambda: junctions(world, net, plan.junctions),
            lambda: repeaters(world, net, plan.segments),
        )
        gone = [world.units[u] for u in sorted(plan.displaced) if u in world.units]
        mark = world.mark()
        while True:
            for emitter in sorted(plan.displaced):
                world.remove_unit(emitter)
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
            Wire(
                net=net.id,
                segments=tuple(plan.segments),
                units=tuple(unit_ids),
                ports=dict(plan.ports),
            )
        )
        if gone:
            short = recover(world, gone)
            if short is not None:
                return refuse(net.id, f"displaced an emitter: {short.detail}")
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
