"""Two cells of one footprint may carry different pins: each gets its own port offsets."""

from kohakulayout.engine import Context
from kohakulayout.ir import Cell, Netlist, Pin
from kohakulayout.solvers.regional.candidates import Proposals
from kohakulayout.templates.physics.gates import LIBRARY, problem


def _cell(cell_id: str, pins: tuple[str, ...]) -> Cell:
    return Cell(
        id=cell_id,
        footprint="AND",
        pins=tuple(
            Pin(id=p, direction="out" if p == "y" else "in", carrier="wire", ports=(p,))
            for p in pins
        ),
    )


def test_port_offsets_follow_the_cell_not_the_footprint() -> None:
    netlist = Netlist(
        pack="gates",
        library=dict(LIBRARY),
        cells={"full": _cell("full", ("a", "b", "y")), "lone": _cell("lone", ("a",))},
    )
    ctx = Context(problem(netlist, width=12, height=8), router=None)
    proposals = Proposals(ctx.world)
    assert set(proposals.port_offsets("full", 0)) == {"a", "b", "y"}
    assert set(proposals.port_offsets("lone", 0)) == {"a"}
    assert (
        proposals.port_offsets("lone", 90)["a"]
        != proposals.port_offsets("lone", 0)["a"]
    )
