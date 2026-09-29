"""Plan → cells: one cell per machine, its lanes as pins on its own ports.

Production machines, Water Treatment Units, Gas Dispersing Units (each with the machines of
its zone in one group), the Automation-Core, outside inputs for every fluid the plan draws
from the world, and the depot side: in Wuling a Depot Bus Port, the sections its bricks need
and the Depot Loaders and Unloaders, all separate cells of the ``bus`` group; in Valley IV
bricks bound to the fixed bus's slots. A pin is one lane of one item; its default port is the
first bound port and its alternatives are every port bound to that item, so placement chooses
the port. Solid lanes go on bricks with the core parked unused, or on the core's depot ports
first when the scenario says ``depot = "core"`` (game-knowledge DEP-02, DEP-06); output lanes
end in Protocol Stashes, which forward to the depot remotely (DEP-14, DEP-21). Fluids arrive
by pipe from outside (RES-09): an ``entry`` cell is one border cell with a pipe lane leaving it
inward at the pipe's rate. Liquids ride conduits (DEP-16, DEP-20): a branching source pin
feeds a Conduit Inlet of its own, every consumer pin is fed by a Conduit Outlet beside it, and
the netlist links each outlet to the inlet that serves it; a liquid drawn from the world comes
out of outlets whose inlet stands at the pump outside the area, so it has no entry at all.
Under ``DIRECT_PIPES`` (off until the lines lay it) liquids are piped machine to machine as
the community's lines do (LOG-02), the world still feeding through outlets.
"""

import logging
import math
from fractions import Fraction

from kohakuefda.flow.lanes import lane_capacity
from kohakuefda.model.cells import (
    BUS_GROUP,
    CellInstance,
    CellKind,
    Constraint,
    LaneKind,
    Pin,
    PortRef,
)
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge
from kohakuefda.model.items import Phase
from kohakuefda.model.layout import Link, Placed
from kohakuefda.model.machines import Machine, Port, PortDir, PortType
from kohakuefda.model.plan import Plan
from kohakuefda.model.rates import lanes_needed
from kohakuefda.model.recipes import Recipe
from kohakuefda.model.scenario import Scenario
from kohakuefda.model.sinks import ZONE_GAS_PER_MIN, ZONE_MACHINE
from kohakuefda.model.units import Hierarchy
from kohakuefda.plan.depot import (
    BUS_PORT,
    BUS_SECTION,
    io_budget,
    laid_limits,
    line_sections,
    sections_needed,
)
from kohakuefda.plan.operating import operating_points, packed_rates
from kohakuefda.plan.units import unit_name
from kohakuefda.plan.zones import assign_zones

log = logging.getLogger(__name__)
CORE = "sp_hub_1"
ENTRY = "entry"
UNLOADER = "unloader_1"
LOADER = "loader_1"
STASH = "storager_1"
INLET = "udpipe_loader_1"
OUTLET = "udpipe_unloader_1"
DIRECT_PIPES = False
DUMP_PREFIX = "dump:"
BUS_SHAPE = "line"
Lane = tuple[str, Fraction]


def _port(machine: Machine, direction: PortDir, index: int) -> Port:
    return next(
        p for p in machine.ports if p.direction is direction and p.index == index
    )


def _ref(port: Port) -> PortRef:
    return PortRef(index=port.index, cell=(port.x, port.y), edge=port.edge)


def activation_port(dataset: Dataset, machine: Machine) -> int:
    """The pipe IN port no recipe of the machine binds: where the activation fluid enters."""
    bound = {
        port
        for recipe in dataset.recipes_of(machine.id)
        for binding in recipe.pipe_in
        for port in binding.ports
    }
    free = [
        p for p in machine.ports_of(PortDir.IN, PortType.PIPE) if p.index not in bound
    ]
    if not free:
        raise ValueError(f"{machine.id} has no free pipe port for activation")
    return free[0].index


def lane_pins(
    dataset: Dataset,
    machine: Machine,
    direction: PortDir,
    item_id: str,
    ports: list[int],
    rate: Fraction,
    taken: set[int],
    pack: bool = False,
) -> list[Pin]:
    """One pin per lane of ``item_id`` over the given ports; the lanes share the alternatives."""
    kind: LaneKind = "pipe" if dataset.items[item_id].phase.is_fluid else "belt"
    rates = packed_rates(rate, lane_capacity(dataset, item_id))
    if rates and not pack:
        rates = (rate / len(rates),) * len(rates)
    candidates = [_port(machine, direction, i) for i in ports if i not in taken]
    if len(candidates) < len(rates):
        raise ValueError(
            f"{machine.id} needs {len(rates)} {direction} ports for {item_id}, has {len(candidates)}"
        )
    alternatives = [_ref(_port(machine, direction, i)) for i in ports]
    pins: list[Pin] = []
    for n, lane_rate in enumerate(rates):
        default = candidates[n]
        taken.add(default.index)
        pins.append(
            Pin(
                id=f"{direction.value}:{item_id}:{n}",
                direction=direction.value,
                kind=kind,
                item_id=item_id,
                rate=lane_rate,
                cell=(default.x, default.y),
                edge=default.edge,
                alternatives=alternatives,
            )
        )
    return pins


def single_cell(
    dataset: Dataset,
    cell_id: str,
    kind: CellKind,
    machine_id: str,
    pins: list[Pin],
    recipe_id: str | None = None,
    mode: str | None = None,
    config: dict[str, str] | None = None,
    env: str | None = None,
    group: str | None = None,
    constraint: Constraint = "free",
) -> CellInstance:
    """A cell holding one machine at the origin with the given pins."""
    machine = dataset.machines[machine_id]
    return CellInstance(
        id=cell_id,
        kind=kind,
        machine_id=machine_id,
        recipe_id=recipe_id,
        width=machine.width,
        height=machine.depth,
        machines=[
            Placed(
                id=f"{cell_id}:m0",
                machine_id=machine_id,
                x=0,
                y=0,
                recipe_id=recipe_id,
                mode=mode,
                config=config or {},
            )
        ],
        pins=pins,
        env=env,
        group=group,
        constraint=constraint,
    )


def recipe_cell(
    dataset: Dataset,
    cell_id: str,
    recipe: Recipe,
    utilisation: Fraction = Fraction(1),
    pack: bool = False,
) -> CellInstance:
    """One recipe's rated input and output lanes; activation remains per built machine."""
    utilisation = operating_points(utilisation, 1)[0]
    machine = dataset.machines[recipe.machine_id]
    taken_in: set[int] = set()
    taken_out: set[int] = set()
    pins: list[Pin] = []
    for stack in recipe.inputs:
        pins += lane_pins(
            dataset,
            machine,
            PortDir.IN,
            stack.item_id,
            dataset.input_ports(recipe, stack.item_id),
            recipe.input_rate(stack.item_id) * utilisation,
            taken_in,
            pack=pack,
        )
    activation = dataset.activations.get(machine.id)
    if activation:
        port = _port(machine, PortDir.IN, activation_port(dataset, machine))
        pins.append(
            Pin(
                id=f"in:{activation.item_id}:activation",
                direction="in",
                kind="pipe",
                item_id=activation.item_id,
                rate=activation.min_rate,
                cell=(port.x, port.y),
                edge=port.edge,
                alternatives=[_ref(port)],
            )
        )
    for stack in recipe.outputs:
        pins += lane_pins(
            dataset,
            machine,
            PortDir.OUT,
            stack.item_id,
            dataset.output_ports(recipe, stack.item_id),
            recipe.output_rate(stack.item_id) * utilisation,
            taken_out,
            pack=pack,
        )
    return single_cell(
        dataset,
        cell_id,
        "recipe",
        machine.id,
        pins,
        recipe_id=recipe.id,
        mode=recipe.mode,
        env=recipe.env,
    )


def single_pin(
    machine: Machine,
    direction: PortDir,
    port_type: PortType,
    item_id: str,
    rate: Fraction,
    pin_id: str,
    net: str | None = None,
) -> Pin:
    """A pin on the machine's first port of the kind, every such port as an alternative."""
    ports = machine.ports_of(direction, port_type)
    first = ports[0]
    return Pin(
        id=pin_id,
        direction=direction.value,
        kind="pipe" if port_type is PortType.PIPE else "belt",
        item_id=item_id,
        rate=rate,
        cell=(first.x, first.y),
        edge=first.edge,
        alternatives=[_ref(p) for p in ports],
        net=net,
    )


def dump_cell(
    dataset: Dataset, cell_id: str, machine_id: str, item_id: str
) -> CellInstance:
    machine = dataset.machines[machine_id]
    rate = dataset.dumps[machine_id].rate_per_machine
    pin = single_pin(
        machine, PortDir.IN, PortType.PIPE, item_id, rate, f"in:{item_id}:0"
    )
    return single_cell(dataset, cell_id, "dump", machine_id, [pin])


def entry_cell(cell_id: str, item_id: str, rate: Fraction) -> CellInstance:
    """An outside input: a 1×1 border cell whose pipe lane leaves it inward (east at rotation 0)."""
    pin = Pin(
        id=f"out:{item_id}:0",
        direction="out",
        kind="pipe",
        item_id=item_id,
        rate=rate,
        cell=(0, 0),
        edge=Edge.E,
        alternatives=[PortRef(index=0, cell=(0, 0), edge=Edge.E)],
    )
    return CellInstance(
        id=cell_id,
        kind="entry",
        machine_id=ENTRY,
        width=1,
        height=1,
        pins=[pin],
        constraint="edge",
    )


def zone_cell(dataset: Dataset, cell_id: str, env: str, group: str) -> CellInstance:
    """A Gas Dispersing Unit with its gas lane, heading the ``group`` of its machines."""
    machine = dataset.machines[ZONE_MACHINE]
    gas = dataset.env_gases[env]
    pin = single_pin(
        machine, PortDir.IN, PortType.PIPE, gas, ZONE_GAS_PER_MIN, f"in:{gas}:0"
    )
    return single_cell(
        dataset, cell_id, "zone", ZONE_MACHINE, [pin], env=env, group=group
    )


def _fixed_pin(
    pin_id: str, direction: str, item_id: str, rate: Fraction, port: Port
) -> Pin:
    return Pin(
        id=pin_id,
        direction=direction,
        kind="belt",
        item_id=item_id,
        rate=rate,
        cell=(port.x, port.y),
        edge=port.edge,
        alternatives=[_ref(port)],
    )


def core_cell(
    dataset: Dataset, cell_id: str, outputs: list[Lane], inputs: list[Lane]
) -> CellInstance:
    """The Automation-Core with out ports sourcing ``outputs`` and in ports taking ``inputs``."""
    machine = dataset.machines[CORE]
    out_ports = machine.ports_of(PortDir.OUT, PortType.BELT)
    in_ports = machine.ports_of(PortDir.IN, PortType.BELT)
    pins: list[Pin] = []
    config: dict[str, str] = {}
    for n, ((item_id, rate), port) in enumerate(zip(outputs, out_ports, strict=False)):
        config[f"out{port.index}"] = item_id
        config[f"out{port.index}_rate"] = str(rate)
        pins.append(_fixed_pin(f"out:{item_id}:{n}", "out", item_id, rate, port))
    for n, ((item_id, rate), port) in enumerate(zip(inputs, in_ports, strict=False)):
        pins.append(
            Pin(
                id=f"in:{item_id}:{n}",
                direction="in",
                kind="belt",
                item_id=item_id,
                rate=rate,
                cell=(port.x, port.y),
                edge=port.edge,
                alternatives=[_ref(p) for p in in_ports],
            )
        )
    return single_cell(dataset, cell_id, "core", CORE, pins, config=config)


def parked_core(dataset: Dataset, cell_id: str) -> CellInstance:
    """The Automation-Core with no lanes: it stays in the area (DEP-03), out of the way."""
    return single_cell(dataset, cell_id, "core", CORE, [], constraint="park")


def brick_cell(
    dataset: Dataset,
    cell_id: str,
    kind: CellKind,
    item_id: str,
    rate: Fraction,
    constraint: Constraint = "slot",
) -> CellInstance:
    """A Depot Loader or Unloader with its belt lane: on a fixed bus slot in Valley IV
    (``slot``), or anywhere it touches a laid bus part in Wuling (``free``)."""
    machine_id = UNLOADER if kind == "unloader" else LOADER
    machine = dataset.machines[machine_id]
    direction = "out" if kind == "unloader" else "in"
    pin = _fixed_pin(
        f"{direction}:{item_id}:0", direction, item_id, rate, machine.ports[0]
    )
    return single_cell(
        dataset,
        cell_id,
        kind,
        machine_id,
        [pin],
        config={"item": item_id} if kind == "unloader" else None,
        group=BUS_GROUP,
        constraint=constraint,
    )


def stash_cell(
    dataset: Dataset, cell_id: str, item_id: str, rate: Fraction
) -> CellInstance:
    """A Protocol Stash taking one belt lane of an output on any of its input ports (DEP-21)."""
    machine = dataset.machines[STASH]
    pin = single_pin(
        machine, PortDir.IN, PortType.BELT, item_id, rate, f"in:{item_id}:0"
    )
    return single_cell(dataset, cell_id, "stash", STASH, [pin])


def conduit_cell(
    dataset: Dataset,
    cell_id: str,
    kind: CellKind,
    item_id: str,
    rate: Fraction,
    net: str,
    config: dict[str, str] | None = None,
) -> CellInstance:
    """A Conduit Inlet (pipe in) or Outlet (pipe out) whose lane is on the net ``net``; an
    outlet fed from outside the area names its item in ``config`` (DEP-20)."""
    inlet = kind == "inlet"
    machine_id = INLET if inlet else OUTLET
    direction = PortDir.IN if inlet else PortDir.OUT
    pin = single_pin(
        dataset.machines[machine_id],
        direction,
        PortType.PIPE,
        item_id,
        rate,
        f"{direction.value}:{item_id}:0",
        net,
    )
    return single_cell(dataset, cell_id, kind, machine_id, [pin], config=config)


def feeders(
    room: list[Fraction], demands: list[Fraction]
) -> list[list[tuple[int, Fraction]]]:
    """Best fit of each demand (largest first) into the room of the feeder with the least that
    holds it whole, else split over feeders in order; per demand its (feeder, rate) shares.
    """
    left = list(room)
    out: list[list[tuple[int, Fraction]]] = [[] for _ in demands]
    for index in sorted(range(len(demands)), key=lambda i: -demands[i]):
        demand = demands[index]
        holders = [i for i, r in enumerate(left) if r >= demand]
        if holders:
            best = min(holders, key=lambda i: left[i])
            out[index].append((best, demand))
            left[best] -= demand
            continue
        for i, r in enumerate(left):
            take = min(r, demand)
            if take > 0:
                out[index].append((i, take))
                left[i] -= take
                demand -= take
            if demand <= 0:
                break
    return out


def bus_part(dataset: Dataset, cell_id: str, machine_id: str) -> CellInstance:
    """A Depot Bus Port or Section: no lanes, a member of the bus group."""
    return single_cell(dataset, cell_id, "depot", machine_id, [], group=BUS_GROUP)


def _lanes(rate: Fraction, capacity: Fraction) -> list[Fraction]:
    """``rate`` split into as few lanes of at most ``capacity`` as possible, evenly."""
    count = lanes_needed(rate, capacity)
    return [rate / count] * count if count else []


def lane_groups(demands: list[Fraction], capacity: Fraction) -> list[Fraction]:
    """Lanes sized by first-fit-decreasing packing of the sink demands, so every sink is fed
    whole by one lane and even splitters deliver the planned rates (game-knowledge JCT-01).
    """
    lanes: list[Fraction] = []
    for demand in sorted(demands, reverse=True):
        for index, used in enumerate(lanes):
            if used + demand <= capacity:
                lanes[index] = used + demand
                break
        else:
            lanes.append(demand)
    return lanes


def supply_lanes(
    cells: list[CellInstance], item_id: str, rate: Fraction, capacity: Fraction
) -> list[Fraction]:
    """Lanes for an item drawn from outside: packed by the sinks' demands when the plan's
    ``rate`` is what they consume, else evenly."""
    demands = [
        p.rate
        for c in cells
        for p in c.pins
        if p.direction == "in" and p.item_id == item_id and p.rate <= capacity
    ]
    if demands and sum(demands, Fraction(0)) == rate:
        return lane_groups(demands, capacity)
    return _lanes(rate, capacity)


class CellFactory:
    """Hands out cell ids and builds cells for one plan."""

    def __init__(
        self,
        dataset: Dataset,
        scenario: Scenario,
        hierarchy: Hierarchy | None = None,
        rated: bool = False,
    ) -> None:
        self.dataset = dataset
        self.scenario = scenario
        self.rated = rated
        self.cells: list[CellInstance] = []
        self.links: list[Link] = []
        self.units: dict[str, tuple[str, int]] = {}
        for tile in hierarchy.tiles if hierarchy is not None else ():
            top = hierarchy.root(tile.id)
            for recipe_id in tile.recipes:
                self.units[recipe_id] = (top, hierarchy.tile(top).copies)

    def _next_id(self, stem: str) -> str:
        return f"c{len(self.cells)}_{stem}"

    def recipe_machines(
        self, recipe_id: str, machines: int, activity: Fraction | None = None
    ) -> None:
        """The recipe's cells, each named for its repeat unit and copy; ``rated`` runs them
        at the plan's exact activity, whole machines before the partial remainder."""
        recipe = self.dataset.recipes[recipe_id]
        top, copies = self.units.get(recipe_id, ("", 1))
        run = max(1, machines // copies)
        if not self.rated or activity is None:
            activity = Fraction(machines)
        for index, duty in enumerate(operating_points(activity, machines)):
            cell = recipe_cell(
                self.dataset,
                self._next_id(recipe.machine_id),
                recipe,
                duty,
                pack=self.rated,
            )
            if top:
                cell.unit = unit_name(top, index // run)
            self.cells.append(cell)

    def zones(self, env: str, count: int) -> int:
        """Zone units for ``env``: the planned ``count`` or more, each heading the group of
        the machines it serves; returns how many zones were made."""
        members = [c for c in self.cells if c.kind == "recipe" and c.env == env]
        groups = assign_zones(members, count)
        for group in groups:
            name = f"zone{sum(1 for c in self.cells if c.kind == 'zone')}"
            self.cells.append(zone_cell(self.dataset, self._next_id("zone"), env, name))
            for member in group:
                member.group = name
        if len(groups) > count:
            log.debug(
                "env %s needed %d zone(s), more than the planned %d",
                env,
                len(groups),
                count,
            )
        return len(groups)

    def dump_machines(self, machine_id: str, item_id: str, units: int) -> None:
        for _ in range(units):
            self.cells.append(
                dump_cell(self.dataset, self._next_id("dump"), machine_id, item_id)
            )

    def entries(self, item_id: str, rate: Fraction) -> None:
        """One outside input per pipe lane of ``rate``, lanes packed by the sinks."""
        capacity = self.dataset.constants.pipe_per_min
        for lane in supply_lanes(self.cells, item_id, rate, capacity):
            self.cells.append(entry_cell(self._next_id("entry"), item_id, lane))

    def stashes(self, item_id: str, rate: Fraction) -> None:
        """One Protocol Stash per belt lane of an output at ``rate``."""
        for lane in _lanes(rate, self.dataset.constants.belt_per_min):
            self.cells.append(
                stash_cell(self.dataset, self._next_id("stash"), item_id, lane)
            )

    def conduits(self, item_id: str, outside: Fraction = Fraction(0)) -> None:
        """Conduits for a liquid already pinned, ``outside`` of it drawn from the world: with
        the fuller side's pin rates scaled down to the other's, each consumer pin is fed by
        the source with the least room that holds its demand whole, else by the world alone
        when it supplies the item and by several sources otherwise; a source that feeds
        more than one consumer gets a Conduit Inlet, and each consumer it feeds a Conduit
        Outlet linked to it; the world feeds through outlets naming the item and linked to
        nothing; any other source pipes to its one consumer when both stand in the same unit
        copy, else it too gets an inlet. Every consumer's feeders share a net keyed to that
        consumer, so every copy of a unit is fed the same way."""
        sources = [
            (c, p)
            for c in self.cells
            for p in c.pins
            if p.item_id == item_id and p.direction == "out" and p.rate > 0
        ]
        sinks = [
            (c, p)
            for c in self.cells
            for p in c.pins
            if p.item_id == item_id and p.direction == "in" and p.rate > 0
        ]
        rooms = [p.rate for _, p in sources] + ([outside] if outside > 0 else [])
        if not rooms or not sinks:
            return
        supply = sum(rooms, Fraction(0))
        demand = sum((p.rate for _, p in sinks), Fraction(0))
        shares = feeders(
            [r * min(1, demand / supply) for r in rooms],
            [p.rate * min(1, supply / demand) for _, p in sinks],
        )
        if outside > 0 and not self.rated:
            world = len(sources)
            shares = [
                [(world, sum(rate for _, rate in share))] if len(share) > 1 else share
                for share in shares
            ]
        if DIRECT_PIPES:
            self.pipes(item_id, sources, sinks, shares)
            return
        fed: dict[int, set[int]] = {}
        for sink, share in enumerate(shares):
            for source, _ in share:
                fed.setdefault(source, set()).add(sink)
        inlets: dict[int, CellInstance] = {}
        for index, (cell, pin) in enumerate(sources):
            takers = fed.get(index, set())
            apart = any(sinks[k][0].unit != cell.unit for k in takers)
            if len(takers) > 1 or apart:
                inlet = conduit_cell(
                    self.dataset, self._next_id("inlet"), "inlet", item_id, pin.rate, ""
                )
                pin.net = inlet.pins[0].net = inlet.id
                inlets[index] = inlet
                self.cells.append(inlet)
        for (cell, pin), share in zip(sinks, shares):
            pin.net = f"{cell.id}_{cell.pins.index(pin)}"
            for source, rate in share:
                if source < len(sources) and source not in inlets:
                    sources[source][1].net = pin.net
                    continue
                from_world = source == len(sources)
                outlet = conduit_cell(
                    self.dataset,
                    self._next_id("outlet"),
                    "outlet",
                    item_id,
                    rate,
                    pin.net,
                    config={"item": item_id} if from_world else None,
                )
                self.cells.append(outlet)
                if not from_world:
                    self.links.append(Link(inlet=inlets[source].id, outlet=outlet.id))

    def pipes(
        self,
        item_id: str,
        sources: list[tuple[CellInstance, Pin]],
        sinks: list[tuple[CellInstance, Pin]],
        shares: list[list[tuple[int, Fraction]]],
    ) -> None:
        """Every connected set of sources and consumers of a liquid on one net, piped
        machine to machine (the synth's pipe trees split and join it); the world feeds a
        consumer through a Conduit Outlet beside it naming the item (DEP-20)."""
        parent: dict[tuple[str, int], tuple[str, int]] = {}

        def find(key: tuple[str, int]) -> tuple[str, int]:
            while parent.setdefault(key, key) != key:
                key = parent[key]
            return key

        for sink, share in enumerate(shares):
            for source, _ in share:
                if source < len(sources):
                    parent[find(("s", source))] = find(("k", sink))
        nets: dict[tuple[str, int], str] = {}
        for sink, ((cell, pin), share) in enumerate(zip(sinks, shares)):
            net = nets.setdefault(
                find(("k", sink)), f"{cell.id}_{cell.pins.index(pin)}"
            )
            pin.net = net
            for source, rate in share:
                if source < len(sources):
                    sources[source][1].net = net
                    continue
                outlet = conduit_cell(
                    self.dataset,
                    self._next_id("outlet"),
                    "outlet",
                    item_id,
                    rate,
                    net,
                    config={"item": item_id},
                )
                self.cells.append(outlet)

    def depot(self, outputs: list[Lane], inputs: list[Lane]) -> None:
        """Solid lanes on the core's ports when the scenario says so; the rest go on bricks,
        with a laid bus's parts in Wuling. The core itself is placed only when the scenario
        asks for it (PLC-05)."""
        core = self.dataset.machines[CORE]
        if self.scenario.depot == "core":
            out_slots = len(core.ports_of(PortDir.OUT, PortType.BELT))
            in_slots = len(core.ports_of(PortDir.IN, PortType.BELT))
            self.cells.append(
                core_cell(
                    self.dataset,
                    self._next_id("core"),
                    outputs[:out_slots],
                    inputs[:in_slots],
                )
            )
            outputs, inputs = outputs[out_slots:], inputs[in_slots:]
        elif self.scenario.core:
            self.cells.append(parked_core(self.dataset, self._next_id("core")))
        if not outputs and not inputs:
            return
        basement = self.dataset.basements.get(self.scenario.basement.basement_id)
        laid = basement is not None and basement.depot.kind == "laid"
        if laid:
            ports, allowed = laid_limits(
                basement.depot, self.scenario.basement.depot_level
            )
            ports = max(1, ports)
            wanted = line_sections if BUS_SHAPE == "line" else sections_needed
            sections = min(allowed, wanted(len(outputs) + len(inputs), ports))
            for _ in range(ports):
                self.cells.append(
                    bus_part(self.dataset, self._next_id("port"), BUS_PORT)
                )
            for _ in range(sections):
                self.cells.append(
                    bus_part(self.dataset, self._next_id("section"), BUS_SECTION)
                )
        constraint: Constraint = "free" if laid else "slot"
        for item_id, rate in outputs:
            self.cells.append(
                brick_cell(
                    self.dataset,
                    self._next_id("unloader"),
                    "unloader",
                    item_id,
                    rate,
                    constraint,
                )
            )
        for item_id, rate in inputs:
            self.cells.append(
                brick_cell(
                    self.dataset,
                    self._next_id("loader"),
                    "loader",
                    item_id,
                    rate,
                    constraint,
                )
            )


def _dump_machines(dataset: Dataset, plan: Plan, machine_id: str) -> dict[str, int]:
    """Dumped items handled by ``machine_id`` with the units each needs."""
    out: dict[str, int] = {}
    for balance in plan.items.values():
        if balance.sink_kind != "dump" or balance.sunk <= 0:
            continue
        sink = dataset.dump_for(balance.item_id)
        if sink and sink.machine_id == machine_id:
            out[balance.item_id] = math.ceil(balance.sunk / sink.rate_per_machine)
    return out


def instantiate(
    dataset: Dataset,
    scenario: Scenario,
    plan: Plan,
    hierarchy: Hierarchy | None = None,
    rated: bool = False,
) -> tuple[list[CellInstance], list[Link]]:
    """Every cell the plan needs (machines, zones, dumps, outside inputs, conduits, stashes
    and the depot side) and the conduit links between inlet and outlet cells.

    Solid supply lanes are packed by their sinks (one lane feeds each machine whole) when the
    depot's slot budget allows, else they are as few as the rate needs.
    """
    factory = CellFactory(dataset, scenario, hierarchy, rated=rated)
    belt = dataset.constants.belt_per_min
    for use in plan.recipes:
        if use.machines <= 0:
            continue
        if use.recipe_id.startswith(DUMP_PREFIX):
            for item_id, units in _dump_machines(dataset, plan, use.machine_id).items():
                factory.dump_machines(use.machine_id, item_id, units)
        else:
            factory.recipe_machines(use.recipe_id, use.machines, use.machines_exact)
    gas_needed: dict[str, Fraction] = {}
    for env, count in plan.zones.items():
        zones = factory.zones(env, count)
        gas = dataset.env_gases[env]
        gas_needed[gas] = gas_needed.get(gas, Fraction(0)) + ZONE_GAS_PER_MIN * zones
    packed: list[Lane] = []
    fewest: list[Lane] = []
    outside: dict[str, Fraction] = {}
    for balance in plan.items.values():
        item = dataset.items[balance.item_id]
        supplied = max(balance.supplied, gas_needed.get(item.id, Fraction(0)))
        if supplied > 0:
            if item.phase is Phase.SOLID:
                lanes = supply_lanes(factory.cells, item.id, supplied, belt)
                packed += [(item.id, lane) for lane in lanes]
                fewest += [(item.id, lane) for lane in _lanes(supplied, belt)]
            elif item.phase is Phase.LIQUID:
                outside[item.id] = supplied
            else:
                factory.entries(item.id, supplied)
        to_depot = balance.delivered + (
            balance.sunk if balance.sink_kind == "depot" else Fraction(0)
        )
        if to_depot > 0 and item.phase is Phase.SOLID:
            factory.stashes(item.id, to_depot)
    for item in dataset.items.values():
        if item.phase is Phase.LIQUID:
            factory.conduits(item.id, outside.get(item.id, Fraction(0)))
    budget = io_budget(dataset, scenario.basement)
    outputs = packed if budget is None or len(packed) <= budget else fewest
    factory.depot(outputs, [])
    log.debug("instantiated %d cell(s) for the plan", len(factory.cells))
    return factory.cells, factory.links
