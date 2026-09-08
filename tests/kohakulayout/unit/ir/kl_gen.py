"""Seeded generators of random problems and layouts for the round-trip properties."""

import random
from fractions import Fraction

from kohakulayout.ir import (
    Carrier,
    Cell,
    Constraint,
    Fabric,
    Footprint,
    Group,
    Layout,
    Module,
    ModulePort,
    Net,
    Netlist,
    PinRef,
    Placement,
    Port,
    Problem,
    Region,
    Reservation,
    Segment,
    Unit,
    Wire,
)
from kohakulayout.ir.geometry import SIDES, side_length

WORDS = ("and", "or", "xor", "buf", "dff", "smelter", "press", "hub")


def _value(rng: random.Random):
    choice = rng.randrange(5)
    if choice == 0:
        return rng.randrange(-5, 50)
    if choice == 1:
        return f"{rng.randrange(1, 40)}/{rng.randrange(1, 7)}"
    if choice == 2:
        return rng.choice([True, False])
    if choice == 3:
        return rng.choice(["north", "fast", "a b", "x-y", "12"])
    return [rng.randrange(9), rng.choice(["a", "b"])]


def _attrs(rng: random.Random) -> dict:
    if rng.random() < 0.5:
        return {}
    return {
        rng.choice(["pk", "other"]): {rng.choice(["zone", "seat", "note"]): _value(rng)}
    }


def random_footprint(rng: random.Random, fid: str, carriers: list[str]) -> Footprint:
    width, height = rng.randrange(1, 5), rng.randrange(1, 5)
    ports = []
    for i in range(rng.randrange(1, 4)):
        side = rng.choice(SIDES)
        ports.append(
            Port(
                id=f"p{i}",
                side=side,
                offset=rng.randrange(side_length(width, height, side)),
                direction=rng.choice(["in", "out", "inout"]),
                carrier=rng.choice(carriers),
            )
        )
    rotations = tuple(
        sorted({0} | {rng.choice([90, 180, 270]) for _ in range(rng.randrange(3))})
    )
    return Footprint(
        id=fid,
        width=width,
        height=height,
        rotations=rotations,
        ports=tuple(ports),
        attrs=_attrs(rng),
    )


def random_problem(seed: int, n_cells: int = 6, hier: bool = False) -> Problem:
    rng = random.Random(seed)
    width, height = rng.randrange(10, 40), rng.randrange(8, 30)
    carriers = {
        "wire": Carrier(id="wire", layer="ground"),
        "pipe": Carrier(id="pipe", layer="overhead", capacity=Fraction(120)),
    }
    every = frozenset((x, y) for y in range(height) for x in range(width))
    ring = frozenset(
        c for c in every if c[0] in (0, width - 1) or c[1] in (0, height - 1)
    )
    regions = {
        "build": Region.of("build", every - ring),
        "ring": Region.of("ring", ring),
    }
    fabric = Fabric(
        width=width,
        height=height,
        layers=("ground", "overhead"),
        carriers=carriers,
        regions=regions,
        entries=("W", "E"),
    )
    library = {
        f"F{i}": random_footprint(rng, f"F{i}", list(carriers))
        for i in range(rng.randrange(2, 5))
    }
    cells: dict[str, Cell] = {}
    for i in range(n_cells):
        fid = rng.choice(list(library))
        constraint = Constraint()
        if rng.random() < 0.3:
            constraint = Constraint(
                kind="edge", attrs={"gen": {"side": rng.choice(SIDES)}}
            )
        cells[f"c{i}"] = Cell(
            id=f"c{i}",
            kind=rng.choice(WORDS),
            footprint=fid,
            constraint=constraint,
            attrs=_attrs(rng),
            needs=("power",) if rng.random() < 0.2 else (),
        )
    netlist = Netlist(pack="gen", library=library, cells=cells)
    outs = [
        (cid, p)
        for cid in cells
        for p in netlist.pins_of(cid)
        if p.direction in ("out", "inout")
    ]
    ins = [
        (cid, p)
        for cid in cells
        for p in netlist.pins_of(cid)
        if p.direction in ("in", "inout")
    ]
    rng.shuffle(outs)
    rng.shuffle(ins)
    nets: dict[str, Net] = {}
    used: set[str] = set()
    for i, (src_cell, src_pin) in enumerate(outs):
        if f"{src_cell}.{src_pin.id}" in used:
            continue
        sinks = [
            (c, p)
            for c, p in ins
            if p.carrier == src_pin.carrier
            and f"{c}.{p.id}" not in used
            and (c, p.id) != (src_cell, src_pin.id)
        ]
        if not sinks:
            continue
        chosen = sinks[: rng.randrange(1, 3)]
        used.add(f"{src_cell}.{src_pin.id}")
        used.update(f"{c}.{p.id}" for c, p in chosen)
        rate = (
            Fraction(rng.randrange(1, 100), rng.randrange(1, 4))
            if src_pin.carrier == "pipe"
            else Fraction(0)
        )
        nets[f"n{i}"] = Net(
            id=f"n{i}",
            kind=rng.choice(["", "flow"]),
            carrier=src_pin.carrier,
            rate=rate,
            sources=(PinRef(cell=src_cell, pin=src_pin.id),),
            sinks=tuple(PinRef(cell=c, pin=p.id) for c, p in chosen),
            attrs=_attrs(rng),
        )
    groups: dict[str, Group] = {}
    if n_cells >= 2 and rng.random() < 0.6:
        members = tuple(sorted(rng.sample(list(cells), 2)))
        groups["g0"] = Group(id="g0", kind="bank", members=members)
        for member in members:
            cells[member] = cells[member].model_copy(update={"group": "g0"})
    modules: dict[str, Module] = {}
    if hier:
        fid = next(iter(library))
        body = Netlist(
            cells={
                "x1": Cell(id="x1", kind="leaf", footprint=fid),
                "x2": Cell(id="x2", kind="leaf", footprint=fid),
            }
        )
        ports = tuple(
            ModulePort(
                id=p.id,
                direction=p.direction,
                carrier=p.carrier,
                inner=PinRef(cell="x1", pin=p.id),
            )
            for p in library[fid].ports[:1]
        )
        modules["M0"] = Module(id="M0", ports=ports, body=body)
        cells["m0"] = Cell(id="m0", kind="M0", module="M0")
    netlist = Netlist(
        pack="gen",
        library=library,
        cells=cells,
        nets=nets,
        groups=groups,
        modules=modules,
        attrs=_attrs(rng),
    )
    return Problem(
        physics="gen@1",
        fabric=fabric,
        netlist=netlist,
        params={"seconds": rng.randrange(1, 900)},
    )


def random_layout(seed: int, problem: Problem) -> Layout:
    """Leaf placements packed along rows, a few random wires in cells form, a unit and a reservation."""
    rng = random.Random(seed)
    netlist = problem.netlist.flatten()
    placements: dict[str, Placement] = {}
    x = y = 0
    row_h = 0
    for cid in sorted(netlist.cells):
        fp = netlist.footprint_for(cid)
        if fp is None:
            continue
        rot = rng.choice(fp.rotations)
        w, h = (fp.width, fp.height) if rot in (0, 180) else (fp.height, fp.width)
        if x + w > problem.fabric.width:
            x, y, row_h = 0, y + row_h + 1, 0
        placements[cid] = Placement(cell=cid, x=x, y=y, rot=rot)
        x += w + 1
        row_h = max(row_h, h)
    wires: dict[str, Wire] = {}
    for nid, net in list(netlist.nets.items())[:2]:
        carrier = problem.fabric.carriers[net.carrier]
        cx, cy = rng.randrange(problem.fabric.width - 4), rng.randrange(
            problem.fabric.height - 1
        )
        cells = tuple((cx + i, cy) for i in range(rng.randrange(1, 5)))
        wires[nid] = Wire(
            net=nid,
            segments=(Segment(carrier=net.carrier, layer=carrier.layer, cells=cells),),
        )
    units = {
        "u0": Unit(
            id="u0",
            kind="jumper",
            footprint="JUMPER",
            x=rng.randrange(problem.fabric.width),
            y=rng.randrange(problem.fabric.height),
            owner="net:n0",
        )
    }
    reservations = (
        Reservation(
            tag="ch",
            layer="ground",
            carrier="wire",
            cells=tuple((i, 0) for i in range(3)),
        ),
    )
    return Layout(
        problem=problem.digest()[:16],
        placements=placements,
        wires=wires,
        units=units,
        reservations=reservations,
        attrs=_attrs(rng),
    )
