"""Geometry rules over a layout: bounds, overlap, segments, ports, counts, zones, power, the
area and its ring, the core, depot bricks on their bus, the bus one cluster, outside inputs
on the border."""

import logging
from itertools import pairwise

from kohakuefda.layout.connect import Connectivity
from kohakuefda.layout.coverage import inside as rect_inside
from kohakuefda.layout.coverage import zone_rect
from kohakuefda.layout.depot_via import BUS_PORT, BUS_SECTION
from kohakuefda.layout.geometry import (
    adjacent,
    inside,
    machine_footprint,
    machine_ports,
)
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import edge_step, rotate_edge
from kohakuefda.model.layout import Layout, Placed, Rect
from kohakuefda.model.machines import GROUND, SKY
from kohakuefda.model.plan import Finding
from kohakuefda.model.sinks import SOURCE_RATES, ZONE_MACHINE
from kohakuefda.route.grid import Occupancy, occupancy_of

log = logging.getLogger(__name__)
PYLON_MACHINES = {"power_diffuser_1", "power_diffuser_2"}
BUS_MACHINES = {BUS_SECTION, BUS_PORT}
DEPOT_MACHINES = {"loader_1", "unloader_1"}
CORE_MACHINES = {"sp_hub_1"}
RING_MACHINES = PYLON_MACHINES | {"power_pole_2", "power_pole_3"}
DEFAULT_PYLON = "power_diffuser_1"


def _rect(dataset: Dataset, placed: Placed) -> Rect:
    width, depth = dataset.machines[placed.machine_id].size(placed.rotation)
    return (placed.x, placed.y, placed.x + width, placed.y + depth)


def ring_allowed(machine_id: str) -> bool:
    """Whether a machine may stand in the ring: pumps, extractors, pylons (REG-03)."""
    return machine_id in RING_MACHINES or (
        machine_id in SOURCE_RATES and machine_id != "unloader_1"
    )


def _finding(rule: str, severity: str, subject: str, message: str) -> Finding:
    return Finding(rule=rule, severity=severity, subject=subject, message=message)


def bounds_and_overlap(occ: Occupancy) -> list[Finding]:
    out: list[Finding] = []
    for layer, cell, name, other in occ.conflicts:
        if layer < 0:
            out.append(
                _finding(
                    "geom.bounds",
                    "error",
                    name,
                    f"{name} leaves the basement at {cell}",
                )
            )
        else:
            layer_name = "ground" if layer == GROUND else "sky"
            out.append(
                _finding(
                    "geom.overlap",
                    "error",
                    name,
                    f"{name} overlaps {other} at {cell} on the {layer_name} layer",
                )
            )
    return out


def segment_shape(dataset: Dataset, layout: Layout) -> list[Finding]:
    """Continuity and run length of every segment."""
    out: list[Finding] = []
    limits = {
        "belt": dataset.constants.belt_run_max,
        "pipe": dataset.constants.pipe_run_max,
    }
    for segment in layout.segments:
        cells = segment.cells
        if not cells:
            out.append(
                _finding(
                    "geom.segment_empty", "error", segment.id, "segment has no cells"
                )
            )
            continue
        for a, b in pairwise(cells):
            if not adjacent(a, b):
                out.append(
                    _finding(
                        "geom.segment_gap",
                        "error",
                        segment.id,
                        f"cells {a} and {b} are not adjacent",
                    )
                )
                break
        if len(set(cells)) != len(cells):
            out.append(
                _finding(
                    "geom.segment_loop",
                    "error",
                    segment.id,
                    "segment visits a cell twice",
                )
            )
        if len(cells) > limits[segment.kind]:
            out.append(
                _finding(
                    "geom.run_length",
                    "error",
                    segment.id,
                    f"{segment.kind} run of {len(cells)} cells exceeds {limits[segment.kind]}",
                )
            )
    return out


def port_connections(conn: Connectivity) -> list[Finding]:
    """Every segment starts at an OUT port and ends at an IN port; ports feed at most one segment."""
    out: list[Finding] = []
    seen_sources: dict[tuple[str, int], str] = {}
    seen_targets: dict[tuple[str, int], str] = {}
    for c in conn.connections.values():
        if c.source is None:
            out.append(
                _finding(
                    "geom.dangling_start",
                    "error",
                    c.segment.id,
                    f"starts at {c.segment.start} with no output port behind it",
                )
            )
        else:
            key = (c.source.owner, c.source.port.index)
            if key in seen_sources:
                out.append(
                    _finding(
                        "geom.port_shared",
                        "error",
                        c.segment.id,
                        f"output port {key} already feeds {seen_sources[key]}",
                    )
                )
            seen_sources[key] = c.segment.id
        if c.target is None:
            out.append(
                _finding(
                    "geom.dangling_end",
                    "error",
                    c.segment.id,
                    f"ends at {c.segment.end} with no input port ahead of it",
                )
            )
        else:
            key = (c.target.owner, c.target.port.index)
            if key in seen_targets:
                out.append(
                    _finding(
                        "geom.merge",
                        "error",
                        c.segment.id,
                        f"input port {key} is also fed by {seen_targets[key]}; merge through a converger",
                    )
                )
            seen_targets[key] = c.segment.id
    return out


def counts(dataset: Dataset, layout: Layout) -> list[Finding]:
    out: list[Finding] = []
    pipe_routers = sum(
        1 for u in layout.units if dataset.logistics[u.unit_id].kind.startswith("pipe")
    )
    if pipe_routers > dataset.constants.fluid_router_limit:
        out.append(
            _finding(
                "geom.fluid_router_count",
                "error",
                "layout",
                f"{pipe_routers} pipe units exceed the limit of {dataset.constants.fluid_router_limit}",
            )
        )
    return out


def conduit_links(dataset: Dataset, layout: Layout) -> list[Finding]:
    out: list[Finding] = []
    by_id = {m.id: m for m in layout.machines}
    for link in layout.links:
        inlet, outlet = by_id.get(link.inlet), by_id.get(link.outlet)
        if inlet is None or outlet is None:
            out.append(
                _finding(
                    "geom.conduit_missing",
                    "error",
                    link.inlet,
                    "conduit link names an unknown end",
                )
            )
            continue
        if not inlet.machine_id.startswith(
            "udpipe_loader"
        ) or not outlet.machine_id.startswith("udpipe_unloader"):
            out.append(
                _finding(
                    "geom.conduit_kind",
                    "error",
                    link.inlet,
                    "a conduit link must join an inlet to an outlet",
                )
            )
        distance = abs(inlet.x - outlet.x) + abs(inlet.y - outlet.y)
        if distance > dataset.constants.conduit_link_max:
            out.append(
                _finding(
                    "geom.conduit_distance",
                    "error",
                    link.inlet,
                    f"conduit ends are {distance} cells apart; the limit is {dataset.constants.conduit_link_max}",
                )
            )
    return out


def zones(dataset: Dataset, layout: Layout) -> list[Finding]:
    """Env recipes must sit fully inside one Gas Dispersing Unit zone (ENV-02); zones must not
    overlap."""
    out: list[Finding] = []
    dispersers = [m for m in layout.machines if m.machine_id == ZONE_MACHINE]
    zone_rects = [
        zone_rect((d.x, d.y), dataset.machines[d.machine_id].width) for d in dispersers
    ]
    for i, a in enumerate(zone_rects):
        for j in range(i + 1, len(zone_rects)):
            b = zone_rects[j]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                out.append(
                    _finding(
                        "geom.zone_overlap",
                        "error",
                        dispersers[i].id,
                        f"gas zones of {dispersers[i].id} and {dispersers[j].id} overlap",
                    )
                )
    for placed in layout.machines:
        recipe = dataset.recipes.get(placed.recipe_id) if placed.recipe_id else None
        if recipe is None or recipe.env is None:
            continue
        rect = _rect(dataset, placed)
        if not any(rect_inside(rect, zone) for zone in zone_rects):
            out.append(
                _finding(
                    "geom.zone_missing",
                    "error",
                    placed.id,
                    f"{placed.id} runs an {recipe.env} recipe but is not fully inside a gas zone",
                )
            )
    return out


def power_coverage(dataset: Dataset, layout: Layout) -> list[Finding]:
    """Every powered machine lies inside a pylon's square (COV-01); the core powers nothing by
    itself (COV-03). A layout with no pylon at all gets one warning."""
    out: list[Finding] = []
    pylons = [m for m in layout.machines if m.machine_id in dataset.pylons]
    powered = [
        m
        for m in layout.machines
        if dataset.machines[m.machine_id].needs_power
        and m.machine_id not in dataset.pylons
        and m.machine_id not in CORE_MACHINES
    ]
    if not pylons:
        if powered:
            out.append(
                _finding(
                    "geom.power",
                    "warning",
                    "layout",
                    f"no pylon placed; {len(powered)} powered machine(s) need one within reach",
                )
            )
        return out
    squares = [
        dataset.pylons[p.machine_id].coverage(
            p.x, p.y, *dataset.machines[p.machine_id].size(p.rotation)
        )
        for p in pylons
    ]
    for placed in powered:
        rect = _rect(dataset, placed)
        if not any(rect_inside(rect, square) for square in squares):
            out.append(
                _finding(
                    "geom.power_uncovered",
                    "error",
                    placed.id,
                    f"{placed.id} is outside every pylon's 12×12 square",
                )
            )
    return out


def core_present(dataset: Dataset, layout: Layout) -> list[Finding]:
    """At most one Automation-Core stands in a layout; a line that does not place one is
    laid out around the core the player already has (PLC-05, DEP-03)."""
    cores = [m for m in layout.machines if m.machine_id in CORE_MACHINES]
    if len(cores) <= 1:
        return []
    return [
        _finding(
            "geom.core_count",
            "error",
            "layout",
            f"{len(cores)} Automation-Cores; a Core AIC Area has one",
        )
    ]


def area_and_ring(dataset: Dataset, layout: Layout) -> list[Finding]:
    """Production stays inside the area; only pumps, extractors and pylons may use the ring
    (REG-03); belts never leave the area (LOG-08)."""
    out: list[Finding] = []
    if layout.area is None:
        return out
    area = layout.area_rect
    for placed in layout.machines:
        if ring_allowed(placed.machine_id):
            continue
        if not rect_inside(_rect(dataset, placed), area):
            out.append(
                _finding(
                    "geom.outside_area",
                    "error",
                    placed.id,
                    f"{placed.id} is not inside the Core AIC Area",
                )
            )
    for segment in layout.belts():
        if any(not rect_inside((x, y, x + 1, y + 1), area) for x, y in segment.cells):
            out.append(
                _finding(
                    "geom.belt_in_ring",
                    "error",
                    segment.id,
                    f"belt {segment.id} leaves the Core AIC Area",
                )
            )
    return out


def _neighbours(cells: set[tuple[int, int]]) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for x, y in cells:
        out.update({(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)})
    return out - cells


def _back_cells(dataset: Dataset, placed: Placed) -> set[tuple[int, int]]:
    """The cells behind a brick's face opposite its port."""
    port = machine_ports(dataset, placed)[0]
    dx, dy = edge_step(rotate_edge(port.edge, 180))
    cells = set(machine_footprint(dataset, placed))
    return {(x + dx, y + dy) for x, y in cells} - cells


def depot_bus(dataset: Dataset, layout: Layout) -> list[Finding]:
    """Depot loaders and unloaders must touch a Depot Bus part with the face opposite their
    port (DEP-06).

    Wuling buses are placed parts of the layout; a Valley IV bus is fixed in the ring and is
    located through the layout's area; without an area the rule is silent for it.
    """
    out: list[Finding] = []
    depots = [m for m in layout.machines if m.machine_id in DEPOT_MACHINES]
    if not depots:
        return out
    bus_cells: set[tuple[int, int]] = set()
    for placed in layout.machines:
        if placed.machine_id in BUS_MACHINES:
            bus_cells.update(machine_footprint(dataset, placed))
    basement = dataset.basements.get(layout.basement.basement_id)
    if basement is not None and basement.depot.kind == "fixed":
        if layout.area is None:
            return out
        ox, oy = layout.origin
        segments = list(basement.depot.segments(layout.basement.depot_level))
        if basement.depot.port is not None:
            segments.append(basement.depot.port)
        for segment in segments:
            bus_cells.update(
                (x + ox, y + oy)
                for x in range(segment.x, segment.x + segment.width)
                for y in range(segment.y, segment.y + segment.depth)
            )
    if not bus_cells:
        out.append(
            _finding(
                "geom.depot_bus",
                "warning",
                "layout",
                "no Depot Bus placed; every loader and unloader must touch one",
            )
        )
        return out
    for placed in depots:
        if not _back_cells(dataset, placed) & bus_cells:
            out.append(
                _finding(
                    "geom.depot_bus",
                    "error",
                    placed.id,
                    f"{placed.id} does not touch a Depot Bus with its back face",
                )
            )
    return out


def bus_connected(dataset: Dataset, layout: Layout) -> list[Finding]:
    """A laid Depot Bus is one cluster of touching parts around a port (DEP-08, DEP-09)."""
    parts = [m for m in layout.machines if m.machine_id in BUS_MACHINES]
    if not parts:
        return []
    cells = {p.id: set(machine_footprint(dataset, p)) for p in parts}
    ports = [p for p in parts if p.machine_id == BUS_PORT]
    if not ports:
        return [
            _finding(
                "geom.bus_connected",
                "error",
                parts[0].id,
                f"{len(parts)} Depot Bus section(s) placed without a Depot Bus Port",
            )
        ]
    reached = {p.id for p in ports}
    frontier = list(ports)
    while frontier:
        current = frontier.pop()
        edge = _neighbours(cells[current.id])
        for other in parts:
            if other.id not in reached and edge & cells[other.id]:
                reached.add(other.id)
                frontier.append(other)
    return [
        _finding(
            "geom.bus_connected",
            "error",
            p.id,
            f"{p.id} does not touch the Depot Bus cluster around the port",
        )
        for p in parts
        if p.id not in reached
    ]


def entries_on_border(layout: Layout) -> list[Finding]:
    """An outside input sits on a border cell of the area with the outside beyond its edge
    (RES-09); no two share a cell."""
    out: list[Finding] = []
    area = layout.area_rect
    seen: set[tuple[int, int]] = set()
    for entry in layout.entries:
        inside_area = rect_inside((entry.x, entry.y, entry.x + 1, entry.y + 1), area)
        ox, oy = entry.outside
        beyond = not rect_inside((ox, oy, ox + 1, oy + 1), area)
        if not inside_area or not beyond:
            out.append(
                _finding(
                    "geom.entry_off_border",
                    "error",
                    entry.id,
                    f"outside input {entry.id} at {entry.cell} is not on the {entry.edge} border of the area",
                )
            )
        if entry.cell in seen:
            out.append(
                _finding(
                    "geom.entry_shared",
                    "error",
                    entry.id,
                    f"two outside inputs share the cell {entry.cell}",
                )
            )
        seen.add(entry.cell)
    return out


def pipes_over_machines(
    dataset: Dataset, layout: Layout, occ: Occupancy
) -> list[Finding]:
    """Pipe cells above machine footprints (recorded as sky-layer overlaps) are called out by name."""
    out: list[Finding] = []
    machine_ids = {m.id for m in layout.machines}
    for layer, cell, name, other in occ.conflicts:
        if layer == SKY and other in machine_ids and name.startswith("pipe"):
            out.append(
                _finding(
                    "geom.pipe_over_machine",
                    "error",
                    name,
                    f"pipe crosses machine {other} at {cell}",
                )
            )
    return out


def check_layout(dataset: Dataset, layout: Layout) -> list[Finding]:
    """All geometry rules in one pass."""
    occ = occupancy_of(dataset, layout)
    conn = Connectivity(dataset, layout)
    findings = bounds_and_overlap(occ)
    findings += segment_shape(dataset, layout)
    findings += port_connections(conn)
    findings += counts(dataset, layout)
    findings += conduit_links(dataset, layout)
    findings += zones(dataset, layout)
    findings += power_coverage(dataset, layout)
    findings += core_present(dataset, layout)
    findings += area_and_ring(dataset, layout)
    findings += depot_bus(dataset, layout)
    findings += bus_connected(dataset, layout)
    findings += entries_on_border(layout)
    findings += pipes_over_machines(dataset, layout, occ)
    for placed in layout.machines:
        if not all(
            inside(c, layout.width, layout.height)
            for c in machine_footprint(dataset, placed)
        ):
            findings.append(
                _finding(
                    "geom.bounds",
                    "error",
                    placed.id,
                    f"{placed.id} extends outside the {layout.width}x{layout.height} basement",
                )
            )
    return findings
