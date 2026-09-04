"""Plan → cells: one cell per machine, its lanes as pins on its own ports.

Production machines, Water Treatment Units, Gas Dispersing Units (each with the machines of
its zone in one group), the Automation-Core, outside inputs for every fluid the plan draws
from the world, and the depot side: in Wuling a Depot Bus Port, the sections its bricks need
and the Depot Loaders and Unloaders, all separate cells of the ``bus`` group; in Valley IV
bricks bound to the fixed bus's slots. A pin is one lane of one item; its default port is the
first bound port and its alternatives are every port bound to that item, so placement chooses
the port. Solid lanes go on bricks with the core parked unused, or on the core's depot ports
first when the scenario says ``depot = "core"`` (game-knowledge DEP-02, DEP-06). Fluids arrive
by pipe from outside (RES-09): an ``entry`` cell is one border cell with a pipe lane leaving it
inward at the pipe's rate.
"""

import logging
import math
from fractions import Fraction

from kohakuefda.flow.lanes import lane_capacity, lane_split
from kohakuefda.layout.depot_via import (
    BUS_PORT,
    BUS_SECTION,
    io_budget,
    laid_limits,
    sections_needed,
)
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
from kohakuefda.model.layout import Placed
from kohakuefda.model.machines import Machine, Port, PortDir, PortType
from kohakuefda.model.plan import Plan
from kohakuefda.model.rates import lanes_needed
from kohakuefda.model.recipes import Recipe
from kohakuefda.model.scenario import Scenario
from kohakuefda.model.sinks import ZONE_GAS_PER_MIN, ZONE_MACHINE
from kohakuefda.plan.zones import assign_zones

log = logging.getLogger(__name__)
CORE = "sp_hub_1"
ENTRY = "entry"
UNLOADER = "unloader_1"
LOADER = "loader_1"
DUMP_PREFIX = "dump:"
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
) -> list[Pin]:
    """One pin per lane of ``item_id`` over the given ports; the lanes share the alternatives."""
    kind: LaneKind = "pipe" if dataset.items[item_id].phase.is_fluid else "belt"
    split = lane_split(rate, lane_capacity(dataset, item_id))
    candidates = [_port(machine, direction, i) for i in ports if i not in taken]
    if len(candidates) < split.ports:
        raise ValueError(
            f"{machine.id} needs {split.ports} {direction} ports for {item_id}, has {len(candidates)}"
        )
    alternatives = [_ref(p) for p in candidates]
    pins: list[Pin] = []
    for n in range(split.ports):
        default = candidates[n]
        taken.add(default.index)
        pins.append(
            Pin(
                id=f"{direction.value}:{item_id}:{n}",
                direction=direction.value,
                kind=kind,
                item_id=item_id,
                rate=split.per_port,
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


def recipe_cell(dataset: Dataset, cell_id: str, recipe: Recipe) -> CellInstance:
    """One machine running ``recipe``: input, activation and output lanes on bound ports."""
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
            recipe.input_rate(stack.item_id),
            taken_in,
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
            recipe.output_rate(stack.item_id),
            taken_out,
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

    def __init__(self, dataset: Dataset, scenario: Scenario) -> None:
        self.dataset = dataset
        self.scenario = scenario
        self.cells: list[CellInstance] = []

    def _next_id(self, stem: str) -> str:
        return f"c{len(self.cells)}_{stem}"

    def recipe_machines(self, recipe_id: str, machines: int) -> None:
        recipe = self.dataset.recipes[recipe_id]
        for _ in range(machines):
            self.cells.append(
                recipe_cell(self.dataset, self._next_id(recipe.machine_id), recipe)
            )

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
            sections = min(allowed, sections_needed(len(outputs) + len(inputs), ports))
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


def instantiate(dataset: Dataset, scenario: Scenario, plan: Plan) -> list[CellInstance]:
    """Every cell the plan needs: machines, zones, dumps, outside inputs, and the depot side.

    Solid supply lanes are packed by their sinks (one lane feeds each machine whole) when the
    depot's slot budget allows, else they are as few as the rate needs.
    """
    factory = CellFactory(dataset, scenario)
    belt = dataset.constants.belt_per_min
    for use in plan.recipes:
        if use.machines <= 0:
            continue
        if use.recipe_id.startswith(DUMP_PREFIX):
            for item_id, units in _dump_machines(dataset, plan, use.machine_id).items():
                factory.dump_machines(use.machine_id, item_id, units)
        else:
            factory.recipe_machines(use.recipe_id, use.machines)
    gas_needed: dict[str, Fraction] = {}
    for env, count in plan.zones.items():
        zones = factory.zones(env, count)
        gas = dataset.env_gases[env]
        gas_needed[gas] = gas_needed.get(gas, Fraction(0)) + ZONE_GAS_PER_MIN * zones
    packed: list[Lane] = []
    fewest: list[Lane] = []
    inputs: list[Lane] = []
    for balance in plan.items.values():
        item = dataset.items[balance.item_id]
        supplied = max(balance.supplied, gas_needed.get(item.id, Fraction(0)))
        if supplied > 0:
            if item.phase is Phase.SOLID:
                lanes = supply_lanes(factory.cells, item.id, supplied, belt)
                packed += [(item.id, lane) for lane in lanes]
                fewest += [(item.id, lane) for lane in _lanes(supplied, belt)]
            else:
                factory.entries(item.id, supplied)
        to_depot = balance.delivered + (
            balance.sunk if balance.sink_kind == "depot" else Fraction(0)
        )
        if to_depot > 0 and item.phase is Phase.SOLID:
            inputs += [(item.id, lane) for lane in _lanes(to_depot, belt)]
    budget = io_budget(dataset, scenario.basement)
    outputs = (
        packed if budget is None or len(packed) + len(inputs) <= budget else fewest
    )
    factory.depot(outputs, inputs)
    log.debug("instantiated %d cell(s) for the plan", len(factory.cells))
    return factory.cells
