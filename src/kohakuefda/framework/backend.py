"""Site adapter: physical queries, transactional edits and portable routed snapshots."""

import json
from types import MappingProxyType

from kohakuefda.framework.assessment import assess
from kohakuefda.framework.config import WORLD_DEFAULTS, settings_of
from kohakuefda.framework.control import Budget, ConfigurationError, Rejected
from kohakuefda.framework.problem import digest
from kohakuefda.layout.board import board_of
from kohakuefda.layout.depot_via import brick_rotation
from kohakuefda.layout.place import catalogue_of
from kohakuefda.layout.site import Site
from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import ROTATIONS
from kohakuefda.model.plan import Plan
from kohakuefda.model.solver import (
    BlockInfo,
    Lane,
    Link,
    PortChoice,
    Problem,
    Screen,
    Snapshot,
    WorldView,
)
from kohakuefda.route.pathfinder import NATIVE


class SiteRouting:
    """Default ordered routing with the existing path effort limits."""

    name = "site-routing-v1"

    def __call__(self, site: Site, required: set[str]) -> bool:
        return site.wire_up(required)


class SiteCoverage:
    name = "site-coverage-v1"

    def __call__(self, site: Site) -> tuple[list, list]:
        return site.default_pylons()


class SiteBackend:
    """Physical backend; solver authors use Context rather than the mutable Site."""

    name = "site-v1"
    capabilities = frozenset(
        {"place", "relocate", "rebuild", "reroute", "port-options"}
    )

    def __init__(
        self,
        problem: Problem,
        budget: Budget,
        settings: dict | None = None,
        backend: str = "auto",
        routing=None,
        coverage=None,
    ) -> None:
        if backend not in ("auto", "python", "native"):
            raise ConfigurationError(f"unknown backend {backend!r}")
        if backend == "native" and not NATIVE:
            raise ConfigurationError("native grid is not installed")
        self.problem = problem
        self.budget = budget
        self.settings = settings_of(WORLD_DEFAULTS, settings)
        dataset = Dataset.model_validate_json(problem.dataset_json)
        netlist = Netlist.model_validate_json(problem.netlist_json)
        self.plan = (
            Plan.model_validate_json(problem.plan_json) if problem.plan_json else None
        )
        if self.settings["pylon"] not in dataset.pylons:
            raise ConfigurationError("unknown pylon")
        if not self.settings["entry_sides"] or set(self.settings["entry_sides"]) - set(
            "NESW"
        ):
            raise ConfigurationError("entry_sides must contain N/E/S/W")
        self.site = Site(
            dataset,
            netlist,
            board_of(dataset, netlist.scenario),
            self.settings,
            budget.check,
            native=backend != "python",
        )
        self.site.router.check = self.path_check
        self.routing = routing or SiteRouting()
        self.coverage = coverage or SiteCoverage()
        self.site.route_service = self.routing
        self.site.cover_service = self.coverage
        self.actual_backend = (
            "native" if self.site.grid.native is not None else "python"
        )
        self.blocks = MappingProxyType(
            {b.id: self.block_info(b) for b in self.site.blocks.values()}
        )
        self.links = tuple(
            Link(w.id, w.source[0], w.sink[0], w.kind, str(w.rate))
            for w in self.site.wires
        )
        self.empty = self.mark()

    @property
    def repeatable_edits(self) -> bool:
        return type(self.routing) is SiteRouting and type(self.coverage) is SiteCoverage

    def path_check(self) -> None:
        self.budget.charge("route_calls")

    def block_info(self, block) -> BlockInfo:
        lanes = tuple(
            Lane(
                p.id,
                p.direction,
                p.kind,
                p.item_id,
                str(p.rate),
                tuple(
                    PortChoice(o.index, o.cell, o.edge.value) for o in p.alternatives
                ),
            )
            for p in block.pins.values()
        )
        return BlockInfo(
            block.id,
            block.fragment.machine_id,
            block.kind,
            block.constraint,
            block.group,
            block.width,
            block.height,
            lanes,
            tuple(tuple(block.offsets(r)) for r in ROTATIONS),
            tuple(tuple(cell for _, cell, _ in block.ports_at(r)) for r in ROTATIONS),
        )

    def view(self, revision: int) -> WorldView:
        site = self.site
        return WorldView(
            revision,
            site.area,
            (site.width, site.height),
            tuple(site.placed.items()),
            tuple((i, tuple(c)) for i, c in site.cells_of.items()),
            frozenset(site.occupied()),
            site.bbox(),
            tuple(site.unplaced()),
            tuple(w.id for w in site.unrouted()),
            site.wire_cells(),
        )

    def mark(self):
        return self.site.snapshot()

    def restore(self, mark) -> None:
        self.site.restore(mark)

    def clear(self) -> None:
        self.restore(self.empty)

    def allowed(self, block_id: str, anchor: tuple) -> None:
        if block_id not in self.blocks:
            raise Rejected(f"unknown block {block_id}", "hard_conflict")
        if (
            len(anchor) != 3
            or any(type(v) is not int for v in anchor)
            or anchor[2] not in ROTATIONS
        ):
            raise Rejected(
                "anchor requires integer x/y and rotation 0/90/180/270", "hard_conflict"
            )
        block = self.blocks[block_id]
        if block.constraint == "slot" and anchor not in self.slot_anchors(block_id):
            raise Rejected("brick is not on a fixed slot", "hard_conflict")
        if block.constraint == "edge" and anchor not in self.border_anchors():
            raise Rejected("entry is not on an allowed border", "hard_conflict")

    def put(self, block_id: str, anchor: tuple) -> None:
        self.budget.check()
        self.allowed(block_id, anchor)
        if block_id in self.site.placed:
            raise Rejected(
                "remove an existing block before replacing it", "hard_conflict"
            )
        if not self.site.place(block_id, *anchor):
            raise Rejected("placement or routing not found under current effort")

    def remove(self, block_id: str) -> None:
        self.budget.check()
        self.site.remove(block_id)

    def reroute(self, routes: tuple[str, ...]) -> None:
        wires = {w.id: w for w in self.site.wires}
        if set(routes) - wires.keys():
            raise Rejected("unknown route", "hard_conflict")
        required = set()
        for name in routes:
            required.update(w.id for w in self.site.router.rip(wires[name]))
        if not self.routing(self.site, required):
            raise Rejected("rerouting not found")

    def slot_anchors(self, block_id: str) -> tuple:
        block = self.site.blocks[block_id]
        machine = self.site.dataset.machines[block.fragment.machine_id]
        return tuple(
            (s.x, s.y, brick_rotation(machine, s.side)) for s in self.site.board.slots
        )

    def border_anchors(self) -> tuple:
        x0, y0, x1, y1 = self.site.area
        result = []
        for side in self.settings["entry_sides"]:
            if side == "N":
                result.extend((x, y0, 90) for x in range(x0, x1))
            elif side == "S":
                result.extend((x, y1 - 1, 270) for x in range(x0, x1))
            elif side == "W":
                result.extend((x0, y, 0) for y in range(y0, y1))
            else:
                result.extend((x1 - 1, y, 180) for y in range(y0, y1))
        return tuple(result)

    def group_anchors(self, block_id: str) -> tuple:
        return tuple(self.site.group_anchors(block_id))

    @property
    def pylon_width(self) -> int:
        return self.site.dataset.machines[self.site.pylon.machine_id].width

    def snapshot_frame(self, snapshot: Snapshot, kind: str) -> dict:
        """Observe a retained realization without reading another candidate's live geometry."""
        raw = json.loads(snapshot.payload)
        layout = json.loads(snapshot.layout_json)
        placement = json.loads(snapshot.placement_json)
        metrics = dict(snapshot.assessment.metrics)
        wires = {w.id: w for w in self.site.wires}
        return {
            "kind": kind,
            "state_id": snapshot.id,
            "blocks": [[i, *anchor] for i, anchor in raw["anchors"]],
            "wires": [
                [i, wires[i].kind, wires[i].net_id, values[0]]
                for i, values in raw["wires"].items()
                if values[0]
            ],
            "placed": len(raw["anchors"]),
            "total": len(self.blocks),
            "failed": [
                i.subject
                for i in snapshot.assessment.issues
                if i.rule == "layout.unrouted"
            ],
            "clean": snapshot.assessment.routed,
            "pylons": placement["pylons"],
            "entries": [
                [e["id"], e["x"], e["y"], e["edge"]] for e in layout["entries"]
            ],
            "terms": metrics,
            "cost": metrics["area"],
            "fits": snapshot.assessment.geometry == "pass",
            "evidence": {
                "routed": snapshot.assessment.routed,
                "rates": snapshot.assessment.rates,
            },
        }

    def frame(self, kind: str) -> dict:
        site = self.site
        if kind == "catalogue":
            return {
                "kind": kind,
                "grid": [site.width, site.height],
                "area": list(site.area),
                "slots": [[s.x, s.y, s.side.value] for s in site.board.slots],
                "blocks": catalogue_of(list(site.blocks.values())),
            }
        return {
            "kind": kind,
            "blocks": [[i, *a] for i, a in site.placed.items()],
            "wires": [
                [w.id, w.kind, w.net_id, list(w.cells)] for w in site.wires if w.cells
            ],
            "placed": len(site.placed),
            "total": len(site.blocks),
            "failed": [w.id for w in site.unrouted()],
            "rect": list(site.bbox()),
            "clean": not site.unplaced() and not site.unrouted(),
            "cost": site.cost(),
            "pylons": [],
            "entries": [],
        }

    def route_state(self) -> dict:
        return {
            w.id: (
                tuple(w.cells),
                w.branch,
                w.join,
                w.source_port.index if w.source_port else None,
                w.sink_port.index if w.sink_port else None,
            )
            for w in self.site.wires
        }

    def payload(self) -> str:
        site = self.site
        raw = {
            "anchors": list(site.placed.items()),
            "wires": self.route_state(),
            "ports": {
                i: {k[1]: v for k, v in b.ports.items()} for i, b in site.blocks.items()
            },
            "trees": [
                [list(key), [w.id for w in wires]]
                for key, wires in site.router.trees.items()
            ],
            "history": [
                [[list(c), v] for c, v in layer.items()] for layer in site.grid.history
            ],
            "settings": self.settings,
        }
        return json.dumps(raw, separators=(",", ":"))

    def capture(self, rates: bool = False, screen: Screen | None = None) -> Snapshot:
        layout, placement, evidence = assess(self.site, self.plan, rates, screen)
        payload = self.payload()
        layout_json, placement_json = (
            layout.model_dump_json(),
            placement.model_dump_json(),
        )
        return Snapshot(
            self.problem.id,
            digest(self.problem.id, payload, layout_json),
            self.name,
            payload,
            layout_json,
            placement_json,
            evidence,
        )

    def load(self, snapshot: Snapshot) -> None:
        if snapshot.problem_id != self.problem.id or snapshot.backend != self.name:
            raise ConfigurationError("snapshot problem or backend differs")
        if snapshot.id != digest(
            snapshot.problem_id, snapshot.payload, snapshot.layout_json
        ):
            raise ConfigurationError("snapshot digest mismatch")
        raw = json.loads(snapshot.payload)
        if raw["settings"] != self.settings:
            raise ConfigurationError("snapshot world settings differ")
        site = self.site
        self.clear()
        for i, values in raw["ports"].items():
            site.blocks[i].ports = {(i, k): v for k, v in values.items()}
        for i, anchor in raw["anchors"]:
            self.allowed(i, tuple(anchor))
            block = site.blocks[i]
            site._occupy(block, block.cells_at(*anchor), *anchor)
        wires = {w.id: w for w in site.wires}
        for name, values in raw["wires"].items():
            wire = wires[name]
            cells, branch, join, source_port, sink_port = values
            wire.cells = [tuple(c) for c in cells]
            wire.branch = tuple(branch) if branch is not None else None
            wire.join = tuple(join) if join is not None else None
            for attr, key, index in (
                ("source_port", wire.source, source_port),
                ("sink_port", wire.sink, sink_port),
            ):
                option = (
                    next(
                        (o for o in site.router.pins[key].options if o.index == index),
                        None,
                    )
                    if index is not None
                    else None
                )
                setattr(wire, attr, option)
                if option is not None:
                    site.router._claim(key, option)
            if wire.cells or wire.branch is not None or wire.join is not None:
                for junction in (wire.branch, wire.join):
                    if junction is not None:
                        site.grid.add_unit(wire.layer, junction)
                site.router.hold(wire)
        site.router.trees = {
            (k[0], tuple(k[1])): [wires[i] for i in ids] for k, ids in raw["trees"]
        }
        for layer, values in enumerate(raw["history"]):
            for cell, value in values:
                site.grid.charge(layer, tuple(cell), value)

    def description(self) -> dict:
        return {
            "backend": self.name,
            "grid": self.actual_backend,
            "routing": self.routing.name,
            "coverage": self.coverage.name,
            "capabilities": sorted(self.capabilities),
        }
