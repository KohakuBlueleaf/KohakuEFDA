"""The Endfield pack as encoded: fabric, carriers, fields, boundaries, each against its fact."""

from fractions import Fraction

import pytest

from kohakuefda.physics import EndfieldPhysics
from kohakuefda.physics.boundaries import ZONE_REACH, edge_anchors, slot_anchors
from kohakuefda.physics.library import (
    BELT,
    BRIDGE,
    CONVERGER,
    PIPE,
    PYLON_EMITTER,
    RUN_LIMIT,
    SPLITTER,
    UNITS,
)
from kohakulayout.ir import (
    Cell,
    Constraint,
    Footprint,
    Group,
    Net,
    Netlist,
    Pin,
    PinRef,
    Placement,
    Port,
    Problem,
)
from kohakulayout.physics import Occupant, get
from kohakulayout.solvers.conformance import level3
from kohakulayout.state import World

BRICK = Footprint(
    id="unloader_1",
    width=3,
    height=1,
    ports=(Port(id="out0", side="S", offset=1, direction="out", carrier=BELT),),
)
ENTRY = Footprint(
    id="entry",
    width=1,
    height=1,
    ports=(Port(id="out0", side="E", offset=0, direction="out", carrier=PIPE),),
)
MACHINE = Footprint(
    id="furnance_1",
    width=3,
    height=3,
    occludes=("sky",),
    ports=(
        Port(id="in0", side="N", offset=1, direction="in", carrier=BELT),
        Port(id="in1", side="W", offset=1, direction="in", carrier=PIPE),
    ),
)
WIDE = Footprint(
    id="assembler_1",
    width=3,
    height=3,
    ports=tuple(
        Port(id=f"out{i}", side="N", offset=i, direction="out", carrier=BELT)
        for i in range(3)
    ),
)
ZONE_UNIT = Footprint(id="vaporizer_1", width=3, height=3)
PART = Footprint(id="log_hongs_bus", width=4, height=8)
PARAMS = {
    "square": [12, 10],
    "ring": 2,
    "slots": ["3:2:N", "6:2:N"],
    "entry_sides": "NEW",
}


def toy_problem() -> Problem:
    physics = EndfieldPhysics()
    library = {fp.id: fp for fp in (BRICK, ENTRY, MACHINE, ZONE_UNIT, PART)}
    cells = {
        "u": Cell(
            id="u",
            kind="unloader",
            footprint=BRICK.id,
            pins=(Pin(id="out.ore.0", direction="out", carrier=BELT, ports=("out0",)),),
            constraint=Constraint(kind="slot"),
            group="bus",
        ),
        "w": Cell(
            id="w",
            kind="unloader",
            footprint=BRICK.id,
            pins=(Pin(id="out.ore.0", direction="out", carrier=BELT, ports=("out0",)),),
            constraint=Constraint(kind="seat"),
            group="bus",
        ),
        "e": Cell(
            id="e",
            kind="entry",
            footprint=ENTRY.id,
            pins=(
                Pin(id="out.water.0", direction="out", carrier=PIPE, ports=("out0",)),
            ),
            constraint=Constraint(kind="edge"),
        ),
        "m": Cell(
            id="m",
            kind="recipe",
            footprint=MACHINE.id,
            pins=(
                Pin(id="in.ore.0", direction="in", carrier=BELT, ports=("in0",)),
                Pin(id="in.water.0", direction="in", carrier=PIPE, ports=("in1",)),
            ),
            needs=("power",),
            group="zone0",
        ),
        "z": Cell(
            id="z",
            kind="zone",
            footprint=ZONE_UNIT.id,
            constraint=Constraint(kind="zone"),
            group="zone0",
        ),
        "p": Cell(
            id="p",
            kind="depot",
            footprint=PART.id,
            constraint=Constraint(kind="cluster"),
            group="bus",
        ),
    }
    nets = {
        "ore": Net(
            id="ore",
            carrier=BELT,
            rate=Fraction(30),
            sources=(PinRef(cell="u", pin="out.ore.0"),),
            sinks=(PinRef(cell="m", pin="in.ore.0"),),
        ),
        "water": Net(
            id="water",
            carrier=PIPE,
            rate=Fraction(60),
            sources=(PinRef(cell="e", pin="out.water.0"),),
            sinks=(PinRef(cell="m", pin="in.water.0"),),
        ),
    }
    netlist = Netlist(
        pack=physics.id,
        library=library,
        cells=cells,
        nets=nets,
        groups={
            "bus": Group(id="bus", members=("u", "w", "p")),
            "zone0": Group(id="zone0", members=("m", "z")),
        },
    )
    return Problem(
        physics=physics.ref,
        fabric=physics.fabric(PARAMS),
        netlist=netlist,
        params=PARAMS,
    )


def wuling_toy() -> Problem:
    """The toy without the Valley IV slots and the brick on them: a laid bus, as Wuling has."""
    base = toy_problem()
    params = {"square": [24, 20], "ring": 2}
    cells = {k: v for k, v in base.netlist.cells.items() if k != "u"}
    nets = {
        k: (
            v.model_copy(update={"sources": (PinRef(cell="w", pin="out.ore.0"),)})
            if k == "ore"
            else v
        )
        for k, v in base.netlist.nets.items()
    }
    groups = {
        "bus": Group(id="bus", members=("w", "p")),
        "zone0": base.netlist.groups["zone0"],
    }
    physics = EndfieldPhysics()
    netlist = base.netlist.model_copy(
        update={"cells": cells, "nets": nets, "groups": groups}
    )
    return Problem(
        physics=physics.ref,
        fabric=physics.fabric(params),
        netlist=netlist,
        params=params,
    )


def test_registration_and_fabric() -> None:
    physics = get("endfield@1")
    assert isinstance(physics, EndfieldPhysics)
    fabric = physics.fabric(PARAMS)
    assert (fabric.width, fabric.height) == (16, 14)
    assert fabric.layers == ("ground", "sky")
    assert (
        fabric.carriers[BELT].capacity == 30 and fabric.carriers[PIPE].capacity == 120
    )
    assert len(fabric.regions["area"].cells()) == 120
    assert len(fabric.regions["ring"].cells()) == 16 * 14 - 120
    assert fabric.regions["build"].cells() == fabric.regions["area"].cells()
    assert set(physics.unit_footprints()) >= set(UNITS) | {PYLON_EMITTER.footprint.id}
    assert toy_problem().check() == []


def test_carrier_rules_follow_the_facts() -> None:
    carriers = EndfieldPhysics().carriers
    belt = Occupant(kind="wire", carrier=BELT)
    pipe = Occupant(kind="wire", carrier=PIPE)
    assert not carriers.may_share(belt, belt) and not carriers.may_share(belt, pipe)
    assert carriers.may_share(belt, Occupant(kind="unit", unit_kind=SPLITTER[BELT]))
    assert not carriers.may_share(belt, Occupant(kind="unit", unit_kind=SPLITTER[PIPE]))
    assert carriers.crossing(BELT, BELT).unit is UNITS[BRIDGE[BELT]]
    assert carriers.crossing(PIPE, PIPE).unit is UNITS[BRIDGE[PIPE]]
    assert carriers.crossing(BELT, PIPE).mode == "forbidden"
    junction = carriers.junction(PIPE)
    assert junction.split is UNITS[SPLITTER[PIPE]]
    assert junction.merge is UNITS[CONVERGER[PIPE]]
    assert carriers.run_limit(BELT) == RUN_LIMIT[BELT] == 110
    assert carriers.run_limit(PIPE) == 80
    assert UNITS[SPLITTER[PIPE]].occludes == ("ground",)
    assert UNITS[SPLITTER[BELT]].occludes == ()
    assert carriers.transfers_through(BRIDGE[BELT], BELT)
    assert not carriers.transfers_through(BRIDGE[BELT], PIPE)


def test_the_pylon_covers_twelve_by_twelve() -> None:
    reach = PYLON_EMITTER.reach
    assert reach.shape == "mask" and len(reach.cells) == 144 and reach.partial
    xs = {dx for dx, _ in reach.cells}
    assert min(xs) == -5 and max(xs) == 6
    fields = EndfieldPhysics().fields
    assert fields.needs(toy_problem().netlist.cells["m"]) == ("power",)
    assert fields.needs(toy_problem().netlist.cells["u"]) == ()


def test_slot_and_edge_anchors() -> None:
    world = World(toy_problem(), EndfieldPhysics(), router=None)
    slots = list(slot_anchors(world, world.netlist.cells["u"]))
    assert [(a.x, a.y, a.rot) for a in slots] == [(3, 2, 0), (6, 2, 0)]
    assert list(world.anchors("u")) == slots
    edges = list(edge_anchors(world, world.netlist.cells["e"]))
    assert all(
        (a.x in (2, 13) or a.y in (2, 11)) and 2 <= a.x <= 13 and 2 <= a.y <= 11
        for a in edges
    )
    assert {a.rot for a in edges if a.x == 2 and 2 < a.y < 11} == {0}
    assert {a.rot for a in edges if a.x == 13 and 2 < a.y < 11} == {180}
    assert {a.rot for a in edges if a.y == 2 and 2 < a.x < 13} == {90}
    default = EndfieldPhysics().fabric({"square": [12, 10], "ring": 2})
    assert default.entries == ("N", "W")


def test_legal_refuses_what_the_game_refuses() -> None:
    world = World(toy_problem(), EndfieldPhysics(), router=None)
    boundaries = world.physics.boundaries
    outside = Placement(cell="m", x=0, y=0, rot=0)
    assert "Core AIC Area" in boundaries.legal(world, outside).detail
    off_slot = Placement(cell="u", x=4, y=4, rot=0)
    assert "slot" in boundaries.legal(world, off_slot).detail
    inward = Placement(cell="e", x=2, y=5, rot=0)
    assert boundaries.legal(world, inward) is None
    outward = Placement(cell="e", x=2, y=5, rot=180)
    assert "inward" in boundaries.legal(world, outward).detail
    assert boundaries.crossing_region(PIPE, "ring")
    assert not boundaries.crossing_region(BELT, "ring")
    assert boundaries.crossing_region(BELT, "area")


def test_every_port_keeps_an_approach() -> None:
    base = toy_problem()
    wide = Cell(
        id="a",
        kind="recipe",
        footprint=WIDE.id,
        pins=tuple(
            Pin(id=f"out.{i}", direction="out", carrier=BELT, ports=(f"out{i}",))
            for i in range(3)
        ),
    )
    nets = {
        f"p{i}": Net(
            id=f"p{i}",
            carrier=BELT,
            rate=Fraction(30),
            sources=(PinRef(cell="a", pin=f"out.{i}"),),
            sinks=(PinRef(cell="m", pin="in.ore.0"),),
        )
        for i in range(3)
    }
    netlist = base.netlist.model_copy(
        update={
            "library": {**base.netlist.library, WIDE.id: WIDE},
            "cells": {**base.netlist.cells, "a": wide},
            "nets": {**base.netlist.nets, **nets},
        }
    )
    world = World(
        base.model_copy(update={"netlist": netlist}), EndfieldPhysics(), router=None
    )
    boundaries = world.physics.boundaries
    under_the_ring = Placement(cell="a", x=4, y=3, rot=0)
    assert "arrive" in boundaries.legal(world, under_the_ring).detail
    one_lower = Placement(cell="a", x=4, y=4, rot=0)
    assert boundaries.legal(world, one_lower) is None
    into_the_ring = Placement(cell="a", x=4, y=2, rot=0)
    assert "closed" in boundaries.legal(world, into_the_ring).detail
    assert boundaries.legal(world, Placement(cell="a", x=4, y=3, rot=180)) is None
    idle = base.netlist.model_copy(
        update={
            "library": {**base.netlist.library, WIDE.id: WIDE},
            "cells": {**base.netlist.cells, "a": wide},
        }
    )
    parked = World(
        base.model_copy(update={"netlist": idle}), EndfieldPhysics(), router=None
    )
    assert parked.physics.boundaries.legal(parked, under_the_ring) is None


def test_zone_and_bus_rules_bind_groups() -> None:
    world = World(toy_problem(), EndfieldPhysics(), router=None)
    with world.transaction():
        assert world.place("z", 4, 4, 0) is None
        far = Placement(cell="m", x=4 + ZONE_REACH + 2, y=4, rot=0)
        assert "zone" in world.physics.boundaries.legal(world, far).detail
        near = Placement(cell="m", x=8, y=4, rot=0)
        assert world.physics.boundaries.legal(world, near) is None
        assert world.place("p", 9, 2, 0) is None
        seated = Placement(cell="w", x=9, y=10, rot=0)
        assert world.physics.boundaries.legal(world, seated) is None
        loose = Placement(cell="w", x=2, y=10, rot=0)
        assert "seat" in world.physics.boundaries.legal(world, loose).detail


def test_a_powered_machine_gets_a_pylon_inside_the_area() -> None:
    world = World(toy_problem(), EndfieldPhysics(), router=None)
    with world.transaction() as tx:
        assert world.place("m", 8, 4, 0) is None
        tx.commit()
    pylons = [u for u in world.units.values() if u.owner == "field:power"]
    assert len(pylons) == 1 and pylons[0].footprint == PYLON_EMITTER.footprint.id
    x0, y0, x1, y1 = 2, 2, 14, 12
    assert x0 <= pylons[0].x and pylons[0].x + 2 <= x1
    assert y0 <= pylons[0].y and pylons[0].y + 2 <= y1
    assert world.field_coverage("power") & set(world.attach_cells("m").values()) or True


@pytest.mark.parametrize("solver", ["inorder", "baseline"])
def test_a_framework_solver_is_a_legal_client_on_the_pack(solver: str) -> None:
    params = {"shrink_rounds": 5} if solver == "baseline" else {}
    assert wuling_toy().check() == []
    report = level3(solver, {"endfield": wuling_toy}, params=params, units=4000)
    assert report.failures == [], report.failures


def test_a_run_ends_at_the_nets_own_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    from kohakuefda.physics import rules
    from kohakulayout.ir import Layout as KlLayout
    from kohakulayout.ir import Segment, Unit, Wire

    monkeypatch.setitem(rules.RUN_LIMIT, BELT, 3)
    cells = tuple((x, 0) for x in range(6))
    splitter = Unit(
        id="u1",
        kind="log_splitter",
        footprint="log_splitter",
        x=3,
        y=0,
        rot=0,
        owner="net:n",
    )
    cut = KlLayout(
        wires={
            "n": Wire(
                net="n",
                segments=(Segment(carrier=BELT, layer="ground", cells=cells),),
                units=("u1",),
            )
        },
        units={"u1": splitter},
    )
    whole = KlLayout(
        wires={
            "n": Wire(
                net="n", segments=(Segment(carrier=BELT, layer="ground", cells=cells),)
            )
        }
    )
    assert list(rules.run_length(None, cut, {})) == []
    found = list(rules.run_length(None, whole, {}))
    assert len(found) == 1 and "run of 6" in found[0].message


def test_a_pin_with_a_choice_of_ports_keeps_one_approach() -> None:
    """A pin that may use a port on either side is legal while one of them keeps an approach."""
    base = toy_problem()
    two_sided = Footprint(
        id="two_sided_1",
        width=3,
        height=3,
        ports=(
            Port(id="out0", side="N", offset=1, direction="out", carrier=BELT),
            Port(id="out1", side="S", offset=1, direction="out", carrier=BELT),
        ),
    )
    cell = Cell(
        id="a",
        kind="recipe",
        footprint=two_sided.id,
        pins=(Pin(id="out", direction="out", carrier=BELT, ports=("out0", "out1")),),
    )
    net = Net(
        id="p",
        carrier=BELT,
        rate=Fraction(30),
        sources=(PinRef(cell="a", pin="out"),),
        sinks=(PinRef(cell="m", pin="in.ore.0"),),
    )
    netlist = base.netlist.model_copy(
        update={
            "library": {**base.netlist.library, two_sided.id: two_sided},
            "cells": {**base.netlist.cells, "a": cell},
            "nets": {**base.netlist.nets, "p": net},
        }
    )
    world = World(
        base.model_copy(update={"netlist": netlist}), EndfieldPhysics(), router=None
    )
    boundaries = world.physics.boundaries
    assert boundaries.legal(world, Placement(cell="a", x=4, y=2, rot=0)) is None
    bound = cell.model_copy(
        update={
            "pins": (Pin(id="out", direction="out", carrier=BELT, ports=("out0",)),)
        }
    )
    world.netlist = netlist.model_copy(update={"cells": {**netlist.cells, "a": bound}})
    assert (
        "closed" in boundaries.legal(world, Placement(cell="a", x=4, y=2, rot=0)).detail
    )
