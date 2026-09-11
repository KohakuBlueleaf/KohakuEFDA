"""A project layout as a framework problem and layout, read from its geometry alone.

Every placed machine is a cell with the machine's footprint; a covering pylon is a field
unit; an outside input is an ``entry`` cell on its border cell; a logistics unit is a
framework unit of the pack's footprint. A segment starts on the cell an OUT port faces and
ends on the cell an IN port faces (its recorded ``entry`` and ``heading`` first, else its
first and last steps; a single cell knows only where it leaves to); a unit whose port
faces another entity's port across a shared edge connects to it directly; a bridge joins
only across opposite edges. The segments and units that touch form one wire, its net
having the OUT pins it leaves from as sources and the IN pins it arrives at as sinks, each
a pin of its cell with the port's item from the recipe or the config. Conduit links ride
in the netlist's ``links`` facts.
"""

import re
from fractions import Fraction
from typing import Any

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge, edge_step
from kohakuefda.model.layout import Cell as XY
from kohakuefda.model.layout import Entry, Layout, Placed, Segment, Unit
from kohakuefda.model.machines import PortDir
from kohakuefda.model.sinks import SOURCE_RATES, ZONE_GAS_PER_MIN, ZONE_MACHINE
from kohakuefda.physics import EndfieldPhysics
from kohakuefda.physics.boundaries import (
    BRICK_KINDS,
    BUS_GROUP,
    CLUSTER,
    PART_KIND,
    SEAT,
    ZONE_KIND,
    ZONE_REACH,
    inside,
    turn,
)
from kohakuefda.physics.fabric import NAMESPACE, slots_of
from kohakuefda.physics.facts import cell_text, pin_fact, rate_text, slot_text
from kohakuefda.physics.library import BELT, GROUND, PIPE, PYLON, PYLON_SIZE, SKY
from kohakuefda.plan.depot import BUS_PORT, BUS_SECTION, fixed_slots
from kohakuefda.synth.footprints import (
    ENTRY,
    ENTRY_FOOTPRINT,
    ENTRY_PORT,
    footprint_of,
    port_id,
)
from kohakuefda.synth.problem import UNPOWERED_KINDS
from kohakulayout.ir import (
    Cell,
    Constraint,
    Group,
    Net,
    Netlist,
    Pin,
    PinRef,
    Placement,
    Problem,
    Wire,
)
from kohakulayout.ir import Layout as FrameworkLayout
from kohakulayout.ir import Segment as FrameworkSegment
from kohakulayout.ir import Unit as FrameworkUnit

CORE = "sp_hub_1"
BRICKS = {"unloader_1": "unloader", "loader_1": "loader"}
PARTS = frozenset({BUS_PORT, BUS_SECTION})
CONDUIT_INLET = "udpipe_loader"
CONDUIT_OUTLET = "udpipe_unloader"
SINKS = frozenset(
    {
        "loader_1",
        "storager_1",
        "sp_hub_1",
        "sp_sub_hub_1",
        "liquid_storager_1",
        "gas_storager_1",
    }
)
LAYERS = {BELT: GROUND, PIPE: SKY}
OPPOSITE = {Edge.N: Edge.S, Edge.S: Edge.N, Edge.E: Edge.W, Edge.W: Edge.E}
ENTRY_SIDES = "NESW"
Step = tuple[int, int]


def kl_name(text: str) -> str:
    """A project id as a framework identifier: every other character becomes an underscore."""
    return re.sub(r"\W", "_", text)


class PortAt:
    """A port of a placed entity in world cells: where it sits, where it faces, what it carries."""

    def __init__(
        self,
        owner: str,
        holder: str,
        port: str,
        direction: str,
        carrier: str,
        cell: XY,
        edge: Edge,
        index: int = 0,
    ) -> None:
        self.owner = owner
        self.holder = holder
        self.port = port
        self.direction = direction
        self.carrier = carrier
        self.cell = cell
        self.edge = edge
        self.index = index
        dx, dy = edge_step(edge)
        self.outside: XY = (cell[0] + dx, cell[1] + dy)


def kind_of(dataset: Dataset, placed: Placed) -> str:
    machine_id = placed.machine_id
    if machine_id == CORE:
        return "core"
    if machine_id in BRICKS:
        return BRICKS[machine_id]
    if machine_id in PARTS:
        return PART_KIND
    if machine_id == ZONE_MACHINE:
        return ZONE_KIND
    if machine_id in dataset.pylons:
        return "pylon"
    if machine_id in dataset.dumps:
        return "dump"
    if machine_id.startswith(CONDUIT_INLET):
        return "inlet"
    if machine_id.startswith(CONDUIT_OUTLET):
        return "outlet"
    return "recipe"


def ports_of_layout(dataset: Dataset, layout: Layout) -> list[PortAt]:
    out: list[PortAt] = []
    for placed in layout.machines:
        machine = dataset.machines[placed.machine_id]
        for port in machine.ports_at(placed.rotation):
            out.append(
                PortAt(
                    kl_name(placed.id),
                    "cell",
                    port_id(port.direction.value, port.index),
                    port.direction.value,
                    port.type.value,
                    (placed.x + port.x, placed.y + port.y),
                    port.edge,
                    port.index,
                )
            )
    for unit in layout.units:
        spec = dataset.logistics[unit.unit_id]
        for port in spec.ports:
            turned = port.rotated(spec.width, spec.depth, unit.rotation)
            out.append(
                PortAt(
                    kl_name(unit.id),
                    "unit",
                    port_id(turned.direction.value, turned.index),
                    turned.direction.value,
                    turned.type.value,
                    (unit.x + turned.x, unit.y + turned.y),
                    turned.edge,
                    turned.index,
                )
            )
    for entry in layout.entries:
        out.append(
            PortAt(
                kl_name(entry.id),
                "entry",
                ENTRY_PORT,
                "out",
                PIPE,
                entry.cell,
                entry.inward,
            )
        )
    return out


def _step(a: XY, b: XY) -> Step:
    return (b[0] - a[0], b[1] - a[1])


def _steps(segment: Segment) -> tuple[Step | None, Step | None]:
    """The travel into the first cell and out of the last: the recorded entry and heading, else the first and last moves."""
    cells = segment.cells
    first = edge_step(segment.entry) if segment.entry is not None else None
    last = edge_step(segment.heading) if segment.heading is not None else None
    if len(cells) >= 2:
        first = first or _step(cells[0], cells[1])
        last = last or _step(cells[-2], cells[-1])
    else:
        first = first or last
        last = last or first
    return first, last


def _prefer(ports: list[PortAt], cell: XY) -> list[PortAt]:
    good = [p for p in ports if p.cell == cell]
    return good or ports


class Connections:
    """Which port every segment leaves from and arrives at, and the direct links between touching entities."""

    def __init__(self, dataset: Dataset, layout: Layout) -> None:
        self.ports = ports_of_layout(dataset, layout)
        self.by_outside: dict[tuple[XY, str, str], list[PortAt]] = {}
        self.by_cell: dict[tuple[XY, str, str], list[PortAt]] = {}
        for port in self.ports:
            self.by_outside.setdefault(
                (port.outside, port.direction, port.carrier), []
            ).append(port)
            self.by_cell.setdefault(
                (port.cell, port.direction, port.carrier), []
            ).append(port)
        self.units = {kl_name(u.id): u for u in layout.units}
        self.ends: dict[str, tuple[PortAt | None, PortAt | None]] = {
            s.id: self._connect(s) for s in layout.segments
        }
        self.links = self._direct_links()

    def _connect(self, segment: Segment) -> tuple[PortAt | None, PortAt | None]:
        if not segment.cells:
            return None, None
        start, end = segment.start, segment.end
        first, last = _steps(segment)
        sources = self.by_outside.get((start, "out", segment.kind), [])
        targets = self.by_outside.get((end, "in", segment.kind), [])
        if first is not None:
            sources = _prefer(sources, (start[0] - first[0], start[1] - first[1]))
        if last is not None:
            targets = _prefer(targets, (end[0] + last[0], end[1] + last[1]))
        if len(segment.cells) == 1:
            target = targets[0] if targets else None
            if target is not None:
                goes_to = (target.owner, target.cell)
                sources = [
                    s for s in sources if (s.owner, s.cell) != goes_to
                ] or sources
            return (sources[0] if sources else None), target
        source = sources[0] if sources else None
        if source is not None:
            came_from = (source.owner, source.cell)
            targets = [t for t in targets if (t.owner, t.cell) != came_from]
        return source, (targets[0] if targets else None)

    def _direct_links(self) -> list[tuple[PortAt, PortAt]]:
        """OUT ports whose facing cell holds another entity's IN port facing back, one end at least a unit (LOG-11)."""
        links: list[tuple[PortAt, PortAt]] = []
        for port in self.ports:
            if port.direction != "out":
                continue
            facing = [
                t
                for t in self.by_cell.get((port.outside, "in", port.carrier), [])
                if t.owner != port.owner
                and t.edge is OPPOSITE[port.edge]
                and (port.holder == "unit" or t.holder == "unit")
            ]
            if facing:
                links.append((port, facing[0]))
        return links


def _node(port: PortAt, dataset: Dataset, units: dict[str, Unit]) -> str:
    """The graph node a port belongs to: a bridge is two nodes, one per axis."""
    kind = dataset.logistics[units[port.owner].unit_id].kind
    if kind.endswith("bridge"):
        axis = "NS" if port.edge in (Edge.N, Edge.S) else "EW"
        return f"unit:{port.owner}:{axis}"
    return f"unit:{port.owner}"


class Component:
    """One wire in the making: its segments, the units it runs through and the pins at its ends."""

    def __init__(self) -> None:
        self.segments: list[Segment] = []
        self.units: list[str] = []
        self.sources: list[PortAt] = []
        self.sinks: list[PortAt] = []
        self.links: list[tuple[PortAt, PortAt]] = []

    @property
    def name(self) -> str:
        """An identifier from the segment ids, else from the units of a direct link."""
        parts = sorted(s.id for s in self.segments) or ["link", *sorted(self.units)]
        return kl_name("__".join(parts))

    @property
    def carrier(self) -> str:
        if self.segments:
            return self.segments[0].kind
        ends = [*self.sources, *self.sinks, *(p for link in self.links for p in link)]
        return ends[0].carrier if ends else BELT


def link_id(source: PortAt, names: dict[str, str]) -> str:
    """A direct link named by the port it leaves from; an entry's owner carries the ``entry:`` prefix."""
    owner = names.get(source.owner, source.owner)
    if source.holder == "entry":
        owner = f"entry:{owner}"
    return f"link:{owner}:{source.index}:{source.edge.value}"


def components_of(
    dataset: Dataset, layout: Layout, conn: Connections
) -> list[Component]:
    parent: dict[str, str] = {}

    def find(key: str) -> str:
        while parent.setdefault(key, key) != key:
            key = parent[key]
        return key

    def join(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    terminals: dict[str, list[tuple[str, PortAt]]] = {}

    def attach(node: str, port: PortAt | None) -> None:
        if port is None:
            return
        if port.holder == "unit":
            join(node, _node(port, dataset, conn.units))
        else:
            terminals.setdefault(node, []).append((port.direction, port))

    for segment in layout.segments:
        node = f"seg:{segment.id}"
        find(node)
        source, target = conn.ends[segment.id]
        attach(node, source)
        attach(node, target)
    link_nodes: list[tuple[str, tuple[PortAt, PortAt]]] = []
    for source, target in conn.links:
        node = (
            _node(source, dataset, conn.units)
            if source.holder == "unit"
            else _node(target, dataset, conn.units)
        )
        find(node)
        attach(node, source)
        attach(node, target)
        link_nodes.append((node, (source, target)))
    groups: dict[str, Component] = {}
    by_id = {s.id: s for s in layout.segments}
    for node in list(parent):
        root = find(node)
        comp = groups.setdefault(root, Component())
        kind, _, rest = node.partition(":")
        if kind == "seg":
            comp.segments.append(by_id[rest])
        elif kind == "unit":
            unit_id = rest.split(":")[0]
            if unit_id not in comp.units:
                comp.units.append(unit_id)
        for direction, port in terminals.get(node, ()):
            (comp.sources if direction == "out" else comp.sinks).append(port)
    for node, link in link_nodes:
        groups[find(node)].links.append(link)
    return [c for c in groups.values() if c.segments or c.links]


def _wire(comp: Component, conn: Connections) -> Wire:
    layer = LAYERS[comp.carrier]
    pieces: list[tuple[XY, ...]] = []
    for segment in comp.segments:
        source, target = conn.ends[segment.id]
        cells: list[XY] = list(segment.cells)
        if source is not None and source.holder == "unit":
            cells.insert(0, source.cell)
        if target is not None and target.holder == "unit":
            cells.append(target.cell)
        pieces.append(tuple(cells))
    for source, target in comp.links:
        if source.holder == "unit" and target.holder == "unit":
            pieces.append((source.cell, target.cell))
    covered = {xy for piece in pieces for xy in piece}
    for unit_id in comp.units:
        xy = (conn.units[unit_id].x, conn.units[unit_id].y)
        if xy not in covered:
            pieces.append((xy,))
            covered.add(xy)
    ports = {
        f"{p.owner}.{p.port}": p.port
        for p in (*comp.sources, *comp.sinks)
        if p.holder != "unit"
    }
    return Wire(
        net=comp.name,
        segments=tuple(
            FrameworkSegment(carrier=comp.carrier, layer=layer, cells=piece)
            for piece in pieces
        ),
        units=tuple(comp.units),
        ports=ports,
    )


def _net(comp: Component) -> Net:
    sources: list[PinRef] = []
    sinks: list[PinRef] = []
    for port in comp.sources:
        ref = PinRef(cell=port.owner, pin=port.port)
        if ref not in sources:
            sources.append(ref)
    for port in comp.sinks:
        ref = PinRef(cell=port.owner, pin=port.port)
        if ref not in sinks:
            sinks.append(ref)
    return Net(
        id=comp.name,
        kind="lane",
        carrier=comp.carrier,
        rate=Fraction(0),
        sources=tuple(sources),
        sinks=tuple(sinks),
        attrs={NAMESPACE: {"net": comp.name}},
    )


def role_of(dataset: Dataset, placed: Placed) -> str:
    """What a machine does to flow: crafter, source, sink, dump, zone, inlet, outlet, or none for a machine without ports."""
    machine_id = placed.machine_id
    if not dataset.machines[machine_id].ports:
        return "none"
    if machine_id in SOURCE_RATES:
        return "source"
    if machine_id in dataset.dumps:
        return "dump"
    if machine_id == ZONE_MACHINE:
        return "zone"
    if machine_id in SINKS:
        return "sink"
    if machine_id.startswith(CONDUIT_INLET):
        return "inlet"
    if machine_id.startswith(CONDUIT_OUTLET):
        return "outlet"
    return "crafter"


def port_specs(
    dataset: Dataset, placed: Placed
) -> dict[tuple[str, int], tuple[str, Fraction]]:
    """The item and rate each port of a placed machine carries, from its role, its recipe and its config."""
    out: dict[tuple[str, int], tuple[str, Fraction]] = {}
    role = role_of(dataset, placed)
    machine = dataset.machines[placed.machine_id]
    recipe = dataset.recipes.get(placed.recipe_id) if placed.recipe_id else None
    if recipe is not None:
        for stack in recipe.outputs:
            for index in dataset.output_ports(recipe, stack.item_id):
                out[("out", index)] = (stack.item_id, recipe.output_rate(stack.item_id))
        for stack in recipe.inputs:
            for index in dataset.input_ports(recipe, stack.item_id):
                out[("in", index)] = (stack.item_id, recipe.input_rate(stack.item_id))
    item = placed.config.get("item", "")
    belt = dataset.constants.belt_per_min
    for port in machine.ports:
        key = (port.direction.value, port.index)
        if key in out:
            continue
        if role == "source" and port.direction is PortDir.OUT:
            rate = (
                Fraction(placed.config["rate"])
                if "rate" in placed.config
                else SOURCE_RATES[placed.machine_id]
            )
            out[key] = (item, rate)
        elif role == "sink" and port.direction is PortDir.OUT:
            named = placed.config.get(f"out{port.index}", "")
            rate = Fraction(placed.config.get(f"out{port.index}_rate", belt))
            out[key] = (named, rate if named else Fraction(0))
        elif role == "dump":
            out[key] = ("", dataset.dumps[placed.machine_id].rate_per_machine)
        elif role == "zone":
            out[key] = ("", ZONE_GAS_PER_MIN)
        else:
            out[key] = (item, Fraction(0))
    return out


def flow_facts(dataset: Dataset, placed: Placed) -> dict[str, Any]:
    """The flow facts of a placed machine beyond its pins: its role, a crafter's needs and products, its activation, a dump's items, an inlet's filter."""
    role = role_of(dataset, placed)
    out: dict[str, Any] = {"role": role}
    recipe = dataset.recipes.get(placed.recipe_id) if placed.recipe_id else None
    if role == "crafter" and recipe is not None:
        out["needs"] = [
            f"{s.item_id}:{rate_text(recipe.input_rate(s.item_id))}"
            for s in recipe.inputs
        ]
        out["makes"] = [
            f"{s.item_id}:{rate_text(recipe.output_rate(s.item_id))}"
            for s in recipe.outputs
        ]
    activation = dataset.activations.get(placed.machine_id)
    if activation is not None:
        out["activation"] = (
            f"{activation.item_id}:{rate_text(activation.min_rate)}"
            f":{rate_text(activation.max_rate)}"
        )
    if role == "dump":
        out["accepts"] = list(dataset.dumps[placed.machine_id].items)
    if role == "inlet":
        out["filter"] = placed.config.get("item", "")
    return out


def params_of_layout(dataset: Dataset, layout: Layout) -> dict[str, Any]:
    """The layout's grid as fabric params: square and ring when the area sits centred, else the whole grid with the area as the entry area."""
    x0, y0, x1, y1 = layout.area_rect
    centred = x0 == y0 and layout.width - x1 == x0 and layout.height - y1 == y0
    out: dict[str, Any] = {
        "square": [x1 - x0, y1 - y0] if centred else [layout.width, layout.height],
        "ring": x0 if centred else 0,
        "entry_area": [x0, y0, x1, y1],
        "entry_sides": ENTRY_SIDES,
    }
    basement = dataset.basements.get(layout.basement.basement_id)
    ox, oy = layout.origin
    if basement is not None and basement.depot.kind == "fixed" and layout.area:
        segments = list(basement.depot.segments(layout.basement.depot_level))
        if basement.depot.port is not None:
            segments.append(basement.depot.port)
        fixed = sorted(
            (x + ox, y + oy)
            for segment in segments
            for y in range(segment.y, segment.y + segment.depth)
            for x in range(segment.x, segment.x + segment.width)
            if 0 <= x + ox < layout.width and 0 <= y + oy < layout.height
        )
        if fixed:
            out["fixed"] = [cell_text(x, y) for x, y in fixed]
        slots = [
            slot_text(s.x + ox, s.y + oy, s.side.value)
            for s in fixed_slots(dataset, layout.basement)
        ]
        if slots:
            out["slots"] = slots
    return out


def _rect(dataset: Dataset, placed: Placed) -> tuple[int, int, int, int]:
    width, depth = dataset.machines[placed.machine_id].size(placed.rotation)
    return (placed.x, placed.y, placed.x + width, placed.y + depth)


class Reverse:
    """One project layout read as a framework problem and layout."""

    def __init__(self, dataset: Dataset, layout: Layout) -> None:
        self.dataset = dataset
        self.layout = layout
        self.physics = EndfieldPhysics()
        self.params = params_of_layout(dataset, layout)
        self.fabric = self.physics.fabric(self.params)
        self.conn = Connections(dataset, layout)
        self.components = components_of(dataset, layout, self.conn)
        self.pins: dict[str, dict[str, PortAt]] = {}
        for comp in self.components:
            for port in (*comp.sources, *comp.sinks):
                if port.holder != "unit":
                    self.pins.setdefault(port.owner, {})[port.port] = port
        self.kinds = {m.id: kind_of(dataset, m) for m in layout.machines}
        self.names: dict[str, str] = {}
        for placed in layout.machines:
            self.names[kl_name(placed.id)] = placed.id
        for unit in layout.units:
            self.names[kl_name(unit.id)] = unit.id
        for entry in layout.entries:
            self.names[kl_name(entry.id)] = entry.id
        self.field_units = {
            m.id
            for m in layout.machines
            if self.kinds[m.id] == "pylon"
            and dataset.pylons[m.machine_id].covers
            and dataset.machines[m.machine_id].size() == (PYLON_SIZE, PYLON_SIZE)
        }

    def bus_grouped(self) -> bool:
        """Whether bricks and parts form the ``bus`` group: parts stand, the bus is laid, or a fixed bus can be located through the area."""
        if any(kind == PART_KIND for kind in self.kinds.values()):
            return True
        basement = self.dataset.basements.get(self.layout.basement.basement_id)
        if basement is None:
            return False
        return basement.depot.kind == "laid" or self.layout.area is not None

    def zone_groups(self) -> dict[str, str]:
        """Each environment machine's zone group: the zone unit whose zone holds it whole."""
        boxes: list[tuple[str, tuple[int, int, int, int]]] = []
        for placed in self.layout.machines:
            if self.kinds[placed.id] == ZONE_KIND:
                x0, y0, x1, y1 = _rect(self.dataset, placed)
                boxes.append(
                    (
                        placed.id,
                        (
                            x0 - ZONE_REACH,
                            y0 - ZONE_REACH,
                            x1 + ZONE_REACH,
                            y1 + ZONE_REACH,
                        ),
                    )
                )
        groups: dict[str, str] = {}
        for index, (unit_id, _) in enumerate(boxes):
            groups[unit_id] = f"{ZONE_KIND}{index}"
        for placed in self.layout.machines:
            recipe = (
                self.dataset.recipes.get(placed.recipe_id) if placed.recipe_id else None
            )
            if recipe is None or recipe.env is None:
                continue
            rect = _rect(self.dataset, placed)
            for unit_id, box in boxes:
                if inside(rect, box):
                    groups[placed.id] = groups[unit_id]
                    break
        return groups

    def cell_of(self, placed: Placed, group: str | None) -> Cell:
        machine = self.dataset.machines[placed.machine_id]
        kind = self.kinds[placed.id]
        specs = port_specs(self.dataset, placed)
        pins: list[Pin] = []
        pin_facts: list[str] = []
        for port in machine.ports:
            pid = port_id(port.direction.value, port.index)
            pins.append(
                Pin(
                    id=pid,
                    direction=port.direction.value,
                    carrier=port.type.value,
                    ports=(pid,),
                )
            )
            item, rate = specs.get(
                (port.direction.value, port.index), ("", Fraction(0))
            )
            pin_facts.append(pin_fact(pid, item, rate))
        info: dict[str, Any] = {
            "machine": placed.machine_id,
            "power": machine.power,
            "pins": pin_facts,
            **flow_facts(self.dataset, placed),
        }
        if placed.recipe_id:
            info["recipe"] = placed.recipe_id
            recipe = self.dataset.recipes.get(placed.recipe_id)
            if recipe is not None and recipe.env:
                info["env"] = recipe.env
        if placed.config:
            info["config"] = [f"{k}:{v}" for k, v in sorted(placed.config.items())]
        constraint = "free"
        if kind in BRICK_KINDS and any(
            (placed.x, placed.y) == (x, y) for x, y, _ in slots_of(self.fabric)
        ):
            constraint = "slot"
        elif group == BUS_GROUP:
            constraint = SEAT if kind in BRICK_KINDS else CLUSTER
        elif kind == ZONE_KIND:
            constraint = ZONE_KIND
        powered = kind not in UNPOWERED_KINDS and machine.needs_power
        return Cell(
            id=kl_name(placed.id),
            kind=kind,
            footprint=placed.machine_id,
            pins=tuple(pins),
            constraint=Constraint(kind=constraint),
            group=group,
            needs=("power",) if powered else (),
            attrs={NAMESPACE: info},
        )

    def entry_cell(self, entry: Entry) -> tuple[Cell, Placement]:
        cell = Cell(
            id=kl_name(entry.id),
            kind=ENTRY,
            footprint=ENTRY,
            pins=(
                Pin(id=ENTRY_PORT, direction="out", carrier=PIPE, ports=(ENTRY_PORT,)),
            ),
            constraint=Constraint(kind="edge"),
            attrs={
                NAMESPACE: {
                    "machine": ENTRY,
                    "power": 0,
                    "role": "entry",
                    "pins": [pin_fact(ENTRY_PORT, entry.item_id, entry.rate)],
                }
            },
        )
        rot = turn("E", entry.inward.value)
        return cell, Placement(cell=kl_name(entry.id), x=entry.x, y=entry.y, rot=rot)

    def problem(self) -> tuple[Problem, FrameworkLayout]:
        library = {}
        cells: dict[str, Cell] = {}
        placements: dict[str, Placement] = {}
        units: dict[str, FrameworkUnit] = {}
        bus = self.bus_grouped()
        zones = self.zone_groups()
        members: dict[str, list[str]] = {}
        for placed in self.layout.machines:
            name = kl_name(placed.id)
            if placed.id in self.field_units:
                units[name] = FrameworkUnit(
                    id=name,
                    kind="power",
                    footprint=PYLON,
                    x=placed.x,
                    y=placed.y,
                    owner="field:power",
                )
                continue
            kind = self.kinds[placed.id]
            group = zones.get(placed.id)
            if bus and (kind == PART_KIND or kind in BRICK_KINDS):
                group = BUS_GROUP
            if placed.machine_id not in library:
                library[placed.machine_id] = footprint_of(
                    self.dataset.machines[placed.machine_id]
                )
            cells[name] = self.cell_of(placed, group)
            placements[name] = Placement(
                cell=name, x=placed.x, y=placed.y, rot=placed.rotation
            )
            if group:
                members.setdefault(group, []).append(name)
        for entry in self.layout.entries:
            library[ENTRY] = ENTRY_FOOTPRINT
            name = kl_name(entry.id)
            cells[name], placements[name] = self.entry_cell(entry)
        nets: dict[str, Net] = {}
        wires: dict[str, Wire] = {}
        owners: dict[str, str] = {}
        for comp in self.components:
            nets[comp.name] = _net(comp)
            wires[comp.name] = _wire(comp, self.conn)
            for unit_id in comp.units:
                owners.setdefault(unit_id, f"net:{comp.name}")
        for unit in self.layout.units:
            name = kl_name(unit.id)
            units[name] = FrameworkUnit(
                id=name,
                kind=unit.unit_id,
                footprint=unit.unit_id,
                x=unit.x,
                y=unit.y,
                owner=owners.get(name, "cell:none"),
                attrs=(
                    {NAMESPACE: {"item": unit.config["item"]}}
                    if unit.config.get("item")
                    else {}
                ),
            )
        netlist = Netlist(
            pack=self.physics.id,
            library=library,
            cells=cells,
            nets=nets,
            groups={
                name: Group(id=name, members=tuple(ids))
                for name, ids in members.items()
            },
            attrs={
                NAMESPACE: {
                    "dataset": self.layout.dataset_version,
                    "basement": self.layout.basement.basement_id,
                    "level": self.layout.basement.level,
                    "depot_level": self.layout.basement.depot_level,
                    "entry": ENTRY,
                    "links": [
                        f"{kl_name(k.inlet)}:{kl_name(k.outlet)}"
                        for k in self.layout.links
                    ],
                }
            },
        )
        problem = Problem(
            physics=self.physics.ref,
            fabric=self.fabric,
            netlist=netlist,
            params=self.params,
        )
        return problem, FrameworkLayout(
            problem=problem.digest(), placements=placements, wires=wires, units=units
        )


def problem_of_layout(
    dataset: Dataset, layout: Layout
) -> tuple[Problem, FrameworkLayout]:
    """The framework problem and layout a project layout describes."""
    return Reverse(dataset, layout).problem()


def project_names(reverse: Reverse, text: str) -> str:
    """The text with every framework id of a machine, unit or entry replaced by the project's."""
    for name, original in reverse.names.items():
        if name != original and name in text:
            text = re.sub(rf"(?<![\w]){re.escape(name)}(?![\w])", original, text)
    return text


__all__ = [
    "Connections",
    "PortAt",
    "Reverse",
    "components_of",
    "flow_facts",
    "kind_of",
    "kl_name",
    "link_id",
    "params_of_layout",
    "port_specs",
    "ports_of_layout",
    "problem_of_layout",
    "project_names",
    "role_of",
]
