"""Steady-state evaluation of a placed layout: rates per segment and utilisation per machine.

Fixed-point relaxation: machines offer output limited by their inputs and by what their outlets
accept; segments carry min(offered, accepted, capacity); splitters share equally over live outputs,
convergers sum; conduit outlets re-emit what their linked inlet takes; dumps accept their items at
the dump rate; a Gas Dispersing Unit takes the zone rate; a machine with an activation entry
stalls below its minimum activation flow. Round-robin over connected output ports models the game's port
polling. Sources emit their default rate or ``config["rate"]``; an outside input (``Layout.entries``)
emits its rate; a depot sink's OUT ports emit the item ``config["out<index>"]`` names (the
Automation-Core's depot ports, game-knowledge DEP-02). Machines without ports (pylons, bus
parts) have no state. The relaxation stops when flows repeat exactly, when rounding them to
``SNAP_DENOMINATOR`` gives a fixed point (tried whenever they move by less than ``EPSILON``
and every ``SNAP_EVERY`` steps), or when they move by less than ``EPSILON`` at all: a
feedback loop approaches its fixed point geometrically and never reaches it by stepping
alone, and its fixed point need not have a small denominator. ``priming`` runs a step with
every crafter treated as fed, which is how a self-seeding loop (planting → seed-picking →
planting) would start in play; the relaxation from a cold start finds the all-zero fixed
point such a loop also has.
"""

import logging
from fractions import Fraction

from kohakuefda.layout.connect import Connection, Connectivity
from kohakuefda.model.base import EfdaModel
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout, Placed, Segment
from kohakuefda.model.rates import Rate
from kohakuefda.model.recipes import Recipe
from kohakuefda.model.sinks import SOURCE_RATES, ZONE_GAS_PER_MIN, ZONE_MACHINE

log = logging.getLogger(__name__)
MAX_ITERATIONS = 1000
EPSILON = Fraction(1, 1_000_000)
SNAP_DENOMINATOR = 3600
SNAP_EVERY = 25
SINK_MACHINES = {
    "loader_1",
    "storager_1",
    "sp_hub_1",
    "sp_sub_hub_1",
    "liquid_storager_1",
    "gas_storager_1",
}
CONDUIT_INLET = "udpipe_loader"
CONDUIT_OUTLET = "udpipe_unloader"
Flows = dict[str, Fraction]


class SegmentFlow(EfdaModel):
    segment_id: str
    items: dict[str, Rate]
    total: Rate
    capacity: Rate


class MachineState(EfdaModel):
    placed_id: str
    machine_id: str
    recipe_id: str | None
    utilisation: Rate
    inputs: dict[str, Rate]
    outputs: dict[str, Rate]
    stalled_by: str = ""


class Evaluation(EfdaModel):
    segments: dict[str, SegmentFlow]
    machines: dict[str, MachineState]
    iterations: int
    converged: bool


def _add(flows: Flows, item_id: str, rate: Fraction) -> None:
    if rate > 0:
        flows[item_id] = flows.get(item_id, Fraction(0)) + rate


def _scale(flows: Flows, factor: Fraction) -> Flows:
    return {k: v * factor for k, v in flows.items()}


def _total(flows: Flows) -> Fraction:
    return sum(flows.values(), Fraction(0))


def _opposite(edge: str) -> str:
    return {"N": "S", "S": "N", "E": "W", "W": "E"}[edge]


class Evaluator:
    """Holds the relaxation state; ``run`` returns the ``Evaluation``."""

    def __init__(self, dataset: Dataset, layout: Layout) -> None:
        self.dataset = dataset
        self.layout = layout
        self.conn = Connectivity(dataset, layout)
        self.segments = list(self.conn.segments.values())
        self.capacities = {s.id: self._capacity(s) for s in self.segments}
        self.offered: dict[str, Flows] = {s.id: {} for s in self.segments}
        self.accepted: dict[str, Fraction] = dict(self.capacities)
        self.flow: dict[str, Flows] = {s.id: {} for s in self.segments}
        self.seen: dict[str, set[str]] = {s.id: set() for s in self.segments}
        self.states: dict[str, MachineState] = {}
        self.conduit_flow: dict[str, Flows] = {}
        self.conduit_accept: dict[str, Fraction] = {}
        self.priming = False

    def _capacity(self, segment: Segment) -> Fraction:
        if segment.kind == "pipe":
            return self.dataset.constants.pipe_per_min
        return self.dataset.constants.belt_per_min

    def _snapshot(self) -> dict[str, Fraction]:
        """Every number the relaxation carries between steps, flattened."""
        out: dict[str, Fraction] = {}
        for segment_id, flows in self.flow.items():
            for item_id, rate in flows.items():
                out[f"flow:{segment_id}:{item_id}"] = rate
            out[f"accept:{segment_id}"] = self.accepted[segment_id]
        for owner, flows in self.conduit_flow.items():
            for item_id, rate in flows.items():
                out[f"conduit:{owner}:{item_id}"] = rate
        for owner, rate in self.conduit_accept.items():
            out[f"conduit_accept:{owner}"] = rate
        return out

    @staticmethod
    def _delta(before: dict[str, Fraction], after: dict[str, Fraction]) -> Fraction:
        """Largest change of any carried number between two snapshots."""
        worst = Fraction(0)
        for key in set(before) | set(after):
            gap = abs(after.get(key, Fraction(0)) - before.get(key, Fraction(0)))
            worst = max(worst, gap)
        return worst

    def _snap(self) -> None:
        """Round every flow and acceptance to a small denominator; a geometric approach
        then lands exactly."""
        for segment_id, flows in self.flow.items():
            self.flow[segment_id] = {
                k: v.limit_denominator(SNAP_DENOMINATOR) for k, v in flows.items()
            }
        for segment_id, accepted in self.accepted.items():
            self.accepted[segment_id] = accepted.limit_denominator(SNAP_DENOMINATOR)

    def _settles(self) -> bool:
        """Whether the snapped flows are a fixed point of one more step."""
        self._snap()
        snapped = self._snapshot()
        self._step()
        return self._delta(snapped, self._snapshot()) == 0

    def run(self) -> Evaluation:
        converged = False
        iterations = 0
        for iterations in range(1, MAX_ITERATIONS + 1):
            before = self._snapshot()
            self._step()
            delta = self._delta(before, self._snapshot())
            if delta == 0:
                converged = True
                break
            if (delta < EPSILON or iterations % SNAP_EVERY == 0) and self._settles():
                converged = True
                break
            if delta < EPSILON:
                converged = True
                break
        if converged:
            log.info("evaluator converged in %d iteration(s)", iterations)
        else:
            log.warning("evaluator did not converge within %d iteration(s)", iterations)
        segments = {
            s.id: SegmentFlow(
                segment_id=s.id,
                items=self.flow[s.id],
                total=_total(self.flow[s.id]),
                capacity=self.capacities[s.id],
            )
            for s in self.segments
        }
        return Evaluation(
            segments=segments,
            machines=self.states,
            iterations=iterations,
            converged=converged,
        )

    def _step(self) -> None:
        for placed in self.layout.machines:
            self._machine(placed)
        for unit_id in [u.id for u in self.layout.units]:
            self._unit(unit_id)
        for entry in self.layout.entries:
            self._share(entry.rate, entry.item_id, self.conn.outgoing(entry.owner))
        for segment in self.segments:
            offered = self.offered[segment.id]
            total = _total(offered)
            limit = min(self.accepted[segment.id], self.capacities[segment.id])
            factor = limit / total if total > limit and total > 0 else Fraction(1)
            self.flow[segment.id] = _scale(offered, factor)
            self.seen[segment.id].update(k for k, v in offered.items() if v > 0)

    def _inflows(self, owner: str) -> Flows:
        flows: Flows = {}
        for c in self.conn.incoming(owner):
            for item_id, rate in self.flow[c.segment.id].items():
                _add(flows, item_id, rate)
        return flows

    def _accept_all(self, owner: str) -> None:
        for c in self.conn.incoming(owner):
            self.accepted[c.segment.id] = self.capacities[c.segment.id]

    def _accept_needs(self, placed: Placed, recipe: Recipe) -> None:
        """A crafter takes what it consumes: the recipe rate split over the segments that have
        ever carried the item (a monotone count, so the relaxation cannot oscillate), activation
        up to its cap."""
        incoming = self.conn.incoming(placed.id)
        carriers: dict[str, int] = {}
        for c in incoming:
            for item_id in self.seen[c.segment.id]:
                carriers[item_id] = carriers.get(item_id, 0) + 1
        activation = self.dataset.activations.get(placed.machine_id)
        for c in incoming:
            carried = self.seen[c.segment.id]
            capacity = self.capacities[c.segment.id]
            if not carried:
                self.accepted[c.segment.id] = capacity
                continue
            total = Fraction(0)
            for item_id in carried:
                if activation and item_id == activation.item_id:
                    total += activation.max_rate
                    continue
                total += recipe.input_rate(item_id) / carriers[item_id]
            self.accepted[c.segment.id] = min(capacity, total)

    def _state(self, placed: Placed, **fields) -> None:
        self.states[placed.id] = MachineState(
            placed_id=placed.id,
            machine_id=placed.machine_id,
            **fields,
        )

    def _machine(self, placed: Placed) -> None:
        machine = self.dataset.machines[placed.machine_id]
        if not machine.ports:
            return
        outgoing = self.conn.outgoing(placed.id)
        if placed.machine_id in SOURCE_RATES:
            self._source(placed, outgoing)
        elif placed.machine_id in self.dataset.dumps:
            self._dump(placed)
        elif placed.machine_id == ZONE_MACHINE:
            self._zone(placed)
        elif placed.machine_id in SINK_MACHINES:
            self._sink(placed)
        elif placed.machine_id.startswith(CONDUIT_INLET):
            self._conduit_inlet(placed)
        elif placed.machine_id.startswith(CONDUIT_OUTLET):
            self._conduit_outlet(placed, outgoing)
        else:
            self._crafter(placed, outgoing)

    def _source(self, placed: Placed, outgoing: list[Connection]) -> None:
        item_id = placed.config.get("item", "")
        rate = (
            Fraction(placed.config["rate"])
            if "rate" in placed.config
            else SOURCE_RATES[placed.machine_id]
        )
        if item_id:
            self._emit(placed.id, {item_id: rate}, outgoing)
        self._state(
            placed,
            recipe_id=None,
            utilisation=Fraction(1) if item_id else Fraction(0),
            inputs={},
            outputs={item_id: rate} if item_id else {},
            stalled_by="" if item_id else "no item chosen",
        )

    def _sink(self, placed: Placed) -> None:
        """A depot sink accepts everything; its OUT ports emit the item ``config`` assigns
        to each (``out<index>``, with ``out<index>_rate``) as a depot source."""
        self._accept_all(placed.id)
        outputs: Flows = {}
        for c in self.conn.outgoing(placed.id):
            index = c.source.port.index if c.source else None
            item_id = placed.config.get(f"out{index}", "")
            if not item_id:
                continue
            rate = Fraction(
                placed.config.get(
                    f"out{index}_rate", self.dataset.constants.belt_per_min
                )
            )
            self._share(rate, item_id, [c])
            _add(outputs, item_id, rate)
        self._state(
            placed,
            recipe_id=None,
            utilisation=Fraction(1),
            inputs=self._inflows(placed.id),
            outputs=outputs,
        )

    def _dump(self, placed: Placed) -> None:
        dump = self.dataset.dumps[placed.machine_id]
        for c in self.conn.incoming(placed.id):
            carried = self.seen[c.segment.id]
            if carried and not carried & set(dump.items):
                self.accepted[c.segment.id] = Fraction(0)
            else:
                self.accepted[c.segment.id] = min(
                    self.capacities[c.segment.id], dump.rate_per_machine
                )
        inputs = self._inflows(placed.id)
        self._state(
            placed,
            recipe_id=None,
            utilisation=min(Fraction(1), _total(inputs) / dump.rate_per_machine),
            inputs=inputs,
            outputs={},
        )

    def _zone(self, placed: Placed) -> None:
        for c in self.conn.incoming(placed.id):
            self.accepted[c.segment.id] = min(
                self.capacities[c.segment.id], ZONE_GAS_PER_MIN
            )
        inputs = self._inflows(placed.id)
        self._state(
            placed,
            recipe_id=None,
            utilisation=min(Fraction(1), _total(inputs) / ZONE_GAS_PER_MIN),
            inputs=inputs,
            outputs={},
            stalled_by="" if inputs else "no gas",
        )

    def _conduit_inlet(self, placed: Placed) -> None:
        wanted = placed.config.get("item", "")
        limit = self.conduit_accept.get(placed.id)
        for c in self.conn.incoming(placed.id):
            carried = self.seen[c.segment.id]
            capacity = self.capacities[c.segment.id]
            if wanted and carried and wanted not in carried:
                self.accepted[c.segment.id] = Fraction(0)
            else:
                self.accepted[c.segment.id] = (
                    capacity if limit is None else min(capacity, limit)
                )
        inflows = self._inflows(placed.id)
        flows = {k: v for k, v in inflows.items() if not wanted or k == wanted}
        self.conduit_flow[placed.id] = flows
        self._state(
            placed,
            recipe_id=None,
            utilisation=Fraction(1) if flows else Fraction(0),
            inputs=inflows,
            outputs={},
            stalled_by="" if flows else "nothing received",
        )

    def _conduit_outlet(self, placed: Placed, outgoing: list[Connection]) -> None:
        inlet = next(
            (k.inlet for k in self.layout.links if k.outlet == placed.id), None
        )
        flows = self.conduit_flow.get(inlet, {}) if inlet else {}
        if inlet:
            self.conduit_accept[inlet] = sum(
                (self.accepted[c.segment.id] for c in outgoing), Fraction(0)
            )
        for item_id, rate in flows.items():
            self._share(rate, item_id, outgoing)
        self._state(
            placed,
            recipe_id=None,
            utilisation=Fraction(1) if flows else Fraction(0),
            inputs={},
            outputs=dict(flows),
            stalled_by="" if inlet else "no conduit link",
        )

    def _crafter(self, placed: Placed, outgoing: list[Connection]) -> None:
        recipe = (
            self.dataset.recipes.get(placed.recipe_id) if placed.recipe_id else None
        )
        if recipe is None:
            self._state(
                placed,
                recipe_id=None,
                utilisation=Fraction(0),
                inputs={},
                outputs={},
                stalled_by="no recipe",
            )
            return
        inflows = self._inflows(placed.id)
        util = Fraction(1)
        stalled = ""
        if not self.priming:
            for stack in recipe.inputs:
                need = recipe.input_rate(stack.item_id)
                have = inflows.get(stack.item_id, Fraction(0))
                if have < need * util:
                    util = have / need
                    if util == 0:
                        stalled = f"no {stack.item_id}"
            activation = self.dataset.activations.get(placed.machine_id)
            if activation and inflows.get(activation.item_id, Fraction(0)) < (
                activation.min_rate
            ):
                util = Fraction(0)
                stalled = (
                    f"activation {activation.item_id} below {activation.min_rate}/min"
                )
        port_connections = {
            stack.item_id: [
                c
                for c in outgoing
                if c.source
                and c.source.port.index
                in self.dataset.output_ports(recipe, stack.item_id)
            ]
            for stack in recipe.outputs
        }
        for stack in recipe.outputs:
            accepted = sum(
                (self.accepted[c.segment.id] for c in port_connections[stack.item_id]),
                Fraction(0),
            )
            produced = recipe.output_rate(stack.item_id)
            if accepted < produced * util:
                util = accepted / produced if produced else util
                if util == 0:
                    stalled = f"no outlet for {stack.item_id}"
        self._accept_needs(placed, recipe)
        outputs = {
            s.item_id: recipe.output_rate(s.item_id) * util for s in recipe.outputs
        }
        for item_id, rate in outputs.items():
            self._share(rate, item_id, port_connections[item_id])
        self._state(
            placed,
            recipe_id=recipe.id,
            utilisation=util,
            inputs=inflows,
            outputs=outputs,
            stalled_by=stalled,
        )

    def _emit(self, owner: str, flows: Flows, outgoing: list[Connection]) -> None:
        for item_id, rate in flows.items():
            self._share(rate, item_id, outgoing)

    def _share(self, rate: Fraction, item_id: str, ports: list[Connection]) -> None:
        """Round-robin over live outlets: each accepting segment gets an equal share, capped."""
        live = [c for c in ports if self.accepted[c.segment.id] > 0]
        for c in ports:
            self.offered[c.segment.id].pop(item_id, None)
        remaining = rate
        pool = list(live)
        while pool and remaining > 0:
            share = remaining / len(pool)
            capped = [c for c in pool if self.accepted[c.segment.id] < share]
            if not capped:
                for c in pool:
                    _add(self.offered[c.segment.id], item_id, share)
                remaining = Fraction(0)
                break
            for c in capped:
                take = self.accepted[c.segment.id]
                _add(self.offered[c.segment.id], item_id, take)
                remaining -= take
                pool.remove(c)

    def _accept_merge(self, incoming: list[Connection], outlet_cap: Fraction) -> None:
        """A single input takes the outlet's room; several inputs each take their capacity
        (the router merges only what the outlet carries, so no arbitration is modelled).
        """
        if len(incoming) == 1:
            c = incoming[0]
            self.accepted[c.segment.id] = min(self.capacities[c.segment.id], outlet_cap)
            return
        for c in incoming:
            self.accepted[c.segment.id] = self.capacities[c.segment.id]

    def _unit(self, unit_id: str) -> None:
        unit = next(u for u in self.layout.units if u.id == unit_id)
        spec = self.dataset.logistics[unit.unit_id]
        incoming = self.conn.incoming(unit_id)
        outgoing = self.conn.outgoing(unit_id)
        inflows = self._inflows(unit_id)
        if spec.kind.endswith("router"):
            outlet_cap = sum(
                (self.accepted[c.segment.id] for c in outgoing), Fraction(0)
            )
            self._accept_merge(incoming, outlet_cap)
            for item_id, rate in inflows.items():
                self._share(rate, item_id, outgoing)
        elif spec.kind.endswith("bridge"):
            for c_in in incoming:
                partner = [
                    c
                    for c in outgoing
                    if c.source
                    and c_in.target
                    and c.source.port.edge == _opposite(c_in.target.port.edge)
                ]
                for c in partner:
                    self.offered[c.segment.id] = dict(self.flow[c_in.segment.id])
                    self.accepted[c_in.segment.id] = self.accepted[c.segment.id]
        elif spec.kind.endswith("control"):
            wanted = unit.config.get("item")
            for c in incoming:
                self.accepted[c.segment.id] = self.capacities[c.segment.id]
            flows = {k: v for k, v in inflows.items() if not wanted or k == wanted}
            for c in outgoing:
                self.offered[c.segment.id] = flows


def evaluate(dataset: Dataset, layout: Layout) -> Evaluation:
    return Evaluator(dataset, layout).run()
