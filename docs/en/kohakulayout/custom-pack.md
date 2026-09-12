---
title: Building your own project
summary: What a project on KohakuLayout owns, walked through on the shipped logic-gates pack, with a fake-2D Minecraft redstone pack as a worked sketch.
tags:
  - kohakulayout
  - physics
  - guide
---

# Building your own project

A project on KohakuLayout is three things: a **physics pack** that says what the grid
means, a **synth** that turns what you want into a netlist, and whatever you do with the
layout that comes back. Placement, routing, rollback, verification, solvers, budgets and
the run service are the framework's, and you reuse them unchanged.

The smallest pack is a fabric and a library. Every other hook has a default in
`BasePhysics`, and each default is the most restrictive answer: cells never share, wires
never cross or branch, runs have no limit, nothing needs a field. You relax exactly what
your game allows. [Physics packs](physics.md) lists every hook with its default.

| you write | it says | hook |
|---|---|---|
| fabric | the board: size, layers, carriers and the layer each runs on, regions, entry sides | `fabric(params)` |
| library | footprints with their ports (side, offset, direction, carrier) | `library()` |
| carriers | which occupants may share a cell, how carriers cross and branch, run limits and repeaters | `carriers` |
| boundaries | where a cell may stand (`anchors`), what is illegal (`legal`), where units may stand | `boundaries` |
| fields | needs such as power, the emitters that meet them, and how to cover them | `fields` |
| rules, objective | the findings a finished layout is checked for, and what "better" weighs | `rules`, `objective` |
| synth | your input turned into a `Netlist`: cells with pins, nets between the pins | yours |

Cells, nets and units carry a `kind` and an `attrs` dictionary under your pack's namespace.
The framework never reads either; your hooks do.

## The shipped example: logic gates

`src/kohakulayout/templates/physics/gates/` is a complete pack with no game in it, and
the framework's own tests run every solver on it. Read it top to bottom; each file is one
hook.

- **`fabric.py`**: a board from `width` and `height`, two layers (`ground`, `overhead`),
  a `wire` carrier on the ground and a `clk` carrier overhead, one `build` region.
- **`library.py`**: 3x3 two-input gates, 2x3 unary gates, a flip-flop with its clock
  port on the south side, 1x1 `IN` and `OUT`, the `JUMPER` unit and the `VDD` emitter.
- **`carriers.py`**: wires of different carriers share a cell; two `wire`s cross only
  through a `JUMPER`; branching is free.
- **`boundaries.py`**: an `edge` constraint pins inputs to the west edge and outputs to
  the east, through `anchors` (where to try) and `legal` (what to refuse).
- **`fields.py`**: the `gates-power` variant, where every gate needs `power` and a
  `VDD` emitter covers a square around it.
- **`rules.py`, `objective.py`**: an edge check and a fan-out limit as findings; area,
  wire cells, jumpers and emitters weighed one each.
- **`synth.py`**: `y = a & b | ~c` lines to a netlist, and random circuits by seed.

A full adder, end to end:

```python
from kohakulayout.engine import Budget
from kohakulayout.pipeline import solve
from kohakulayout.templates.physics.gates import from_expressions, problem

netlist = from_expressions("""
s = a ^ b ^ cin
cout = a & b | cin & (a ^ b)
""")
result = solve(problem(netlist, width=24, height=12), solver="regional", budget=Budget(seconds=10))
print(result.outcome, result.assessment.complete)  # complete True
```

`result.layout` holds the placements, wires and units; `result.assessment` holds the
metrics and the findings. The same problem written as a `.kl` file goes through the
command line: `kl solve problem.kl --solver regional --seconds 10 -o layout.kl`.

## A worked sketch: Minecraft redstone in fake 2D

Redstone maps onto the hooks almost one for one, which makes it a good second example.
This is a sketch: it is not shipped, and it stops where the framework's model and the
game's part ways (below). The code on this page runs as written, and on a 40-wide board
the router places four repeaters to keep every run within reach.

| redstone | the pack |
|---|---|
| dust | the `dust` carrier on the `ground` layer |
| a signal fades after 15 blocks, a repeater restores it | `run_limit("dust") = 15`, `repeater("dust") = REPEATER`; the router puts a repeater on a straight cell before the limit |
| dust branches wherever it meets | `junction` is `free` |
| an OR is dust from two sources meeting | a net with two sources; no cell needed |
| two lines cross by going up a block | a second layer, `bridge`, and `crossing` through the `BRIDGE` unit: the "fake" in fake 2D |
| a torch on a block inverts | a `TORCH` cell with one input and one output |
| levers and lamps at the edge of the build | an `edge` constraint read by `boundaries` |

```python
"""A fake-2D redstone pack: dust on the ground layer, a bridge one block up where two lines cross."""

from typing import Any

from collections.abc import Iterable

from kohakulayout.ir import Carrier, Cell, Fabric, Footprint, Placement, Port, Problem, Refusal, Region
from kohakulayout.ir.geometry import rotate_size
from kohakulayout.physics import (
    Anchor,
    BasePhysics,
    DefaultBoundaries,
    free_anchors,
    CrossingRule,
    DefaultCarriers,
    JunctionRule,
    Occupant,
    register,
)

BRIDGE = Footprint(id="BRIDGE", width=1, height=1, layer="bridge", rotations=(0,))
REPEATER = Footprint(id="REPEATER", width=1, height=1, rotations=(0, 90, 180, 270))
SIGNAL_RANGE = 15


def part(id: str, width: int, ins: int, outs: int) -> Footprint:
    ports = [Port(id=f"i{n}", side="W", offset=n, direction="in", carrier="dust") for n in range(ins)]
    ports += [Port(id=f"o{n}", side="E", offset=n, direction="out", carrier="dust") for n in range(outs)]
    return Footprint(id=id, width=width, height=max(ins, outs, 1), ports=tuple(ports))


LIBRARY = {
    "LEVER": part("LEVER", 1, 0, 1),
    "LAMP": part("LAMP", 1, 1, 0),
    "TORCH": part("TORCH", 2, 1, 1),
}


class Dust(DefaultCarriers):
    def may_share(self, a: Occupant, b: Occupant) -> bool:
        wire, other = (a, b) if a.kind == "wire" else (b, a)
        return wire.kind == "wire" and other.kind == "unit" and other.unit_kind == BRIDGE.id

    def crossing(self, a: str, b: str) -> CrossingRule:
        return CrossingRule(mode="unit", unit=BRIDGE)

    def junction(self, carrier: str) -> JunctionRule:
        return JunctionRule(mode="free")

    def run_limit(self, carrier: str) -> int | None:
        return SIGNAL_RANGE

    def repeater(self, carrier: str) -> Footprint | None:
        return REPEATER

    def transfers_through(self, unit_kind: str, carrier: str) -> bool:
        return unit_kind in (BRIDGE.id, REPEATER.id)


def side_of(cell: Cell) -> str | None:
    """The board edge an ``edge`` cell must touch."""
    if cell.constraint.kind != "edge":
        return None
    return cell.constraint.attrs.get("redstone", {}).get("side")


class Edges(DefaultBoundaries):
    """Levers and lamps pinned to a board edge; everything else anywhere."""

    def anchors(self, world: Any, cell: Cell) -> Iterable[Anchor]:
        side, fp = side_of(cell), world.footprint_of(cell.id)
        if side is None:
            yield from free_anchors(world, cell)
            return
        for rot in (0,):
            w, h = rotate_size(fp.width, fp.height, rot)
            x = 0 if side == "W" else world.fabric.width - w
            for y in range(world.fabric.height - h + 1):
                yield Anchor(x=x, y=y, rot=rot)

    def legal(self, world: Any, placement: Placement) -> Refusal | None:
        side = side_of(world.netlist.cells[placement.cell])
        fp = world.footprint_of(placement.cell)
        x = 0 if side == "W" else world.fabric.width - fp.width
        if side is not None and (placement.x != x or placement.rot != 0):
            return Refusal(stage="legal", subject=f"cell:{placement.cell}", detail=f"must touch the {side} edge")
        return None


@register
class RedstonePhysics(BasePhysics):
    id = "redstone"
    version = "1"

    def __init__(self) -> None:
        super().__init__()
        self.carriers = Dust()
        self.boundaries = Edges()

    def fabric(self, params: dict[str, Any]) -> Fabric:
        w, h = int(params.get("width", 32)), int(params.get("height", 16))
        return Fabric(
            width=w,
            height=h,
            layers=("ground", "bridge"),
            carriers={"dust": Carrier(id="dust", layer="ground")},
            regions={"build": Region.of("build", {(x, y) for y in range(h) for x in range(w)})},
        )

    def library(self) -> dict[str, Footprint]:
        return dict(LIBRARY)

    def unit_footprints(self) -> dict[str, Footprint]:
        return {BRIDGE.id: BRIDGE, REPEATER.id: REPEATER}


def problem(netlist: Any, **params: Any) -> Problem:
    physics = RedstonePhysics()
    return Problem(physics=physics.ref, fabric=physics.fabric(params), netlist=netlist, params=params)
```

A lever driving a lamp through a torch, and a second lever driving a lamp directly:

```python
from kohakulayout.engine import Budget
from kohakulayout.ir import Cell, Constraint, Net, Netlist, PinRef
from kohakulayout.pipeline import solve
from redstone import LIBRARY, problem

def cell(id, fp, side=None):
    constraint = Constraint(kind="edge", attrs={"redstone": {"side": side}}) if side else Constraint()
    return Cell(id=id, footprint=fp, kind=fp, constraint=constraint)

def net(id, src, *sinks):
    return Net(id=id, carrier="dust", sources=(PinRef(cell=src[0], pin=src[1]),),
               sinks=tuple(PinRef(cell=c, pin=p) for c, p in sinks))

cells = {"a": cell("a", "LEVER", "W"), "b": cell("b", "LEVER", "W"), "n": cell("n", "TORCH"),
         "x": cell("x", "LAMP", "E"), "y": cell("y", "LAMP", "E")}
nets = {"na": net("na", ("a", "o0"), ("n", "i0")), "nn": net("nn", ("n", "o0"), ("x", "i0")),
        "nb": net("nb", ("b", "o0"), ("y", "i0"))}
netlist = Netlist(pack="redstone", library=dict(LIBRARY), cells=cells, nets=nets)
for w in (14, 40):
    r = solve(problem(netlist, width=w, height=10), solver="regional", seed=0, budget=Budget(seconds=10))
    kinds = sorted(u.kind for u in r.layout.units.values())
    print(w, r.outcome, r.assessment.complete, r.assessment.metrics.get("area"), kinds)
```

### Where the sketch stops

- **Dust joins its neighbours.** Two different nets' dust side by side connect in the
  game, while the framework only knows cells, not adjacency. Route on a grid where one
  cell is two blocks and let your export fill the gaps, or add a rule that reports
  side-by-side foreign dust as a finding.
- **Direction and delay.** A repeater faces one way and delays a tick; a torch burns
  out. The pack places repeaters where the run needs them. Facing them along the path
  and timing the circuit are your export's and your checker's job.
- **True 3D.** Fake 2D gives crossings one extra layer. Circuits that stack are several
  layers with units between them, which is a larger pack than this one.
- **Logic is not simulated.** The framework's flow evaluator settles rates on a
  steady-state model. It does not evaluate a truth table, so a logic check belongs in
  your rules or your own tests.

## Checklist for a new pack

1. Subclass `BasePhysics`, set `id` and `version`, override `fabric` and `library`, and
   register it with `@register` (or the `kohakulayout.physics` entry point).
2. Relax the carrier rules your game allows, one method at a time, and list the units
   the router may place in `unit_footprints`.
3. Add `anchors` and `legal` for any placement constraint, and fields only when
   something needs coverage.
4. Write a synth that builds a `Netlist`, then run `solve` with the `inorder` solver for
   a first answer and `regional` for a real one.
5. Put the pack under the conformance suite ([Conformance and gates](conformance.md)) so
   every solver is held to the same obligations on your grid.

Past the pack, the override points are the router's `TreePolicy` (how a net's lanes are
ordered and where they may start), the solvers' `Proposals` and `Search` (how anchors are
ranked and cells chosen), passes and plugins. KohakuEFDA uses all of them and stays out
of the framework: `kohakulayout` imports nothing from `kohakuefda`, and a test fails the
moment it does.
