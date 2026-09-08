"""Level 1 on the power variant: needs, the emitter, its reach, the pack id."""

from importlib.resources import files

from kohakulayout.ir import Cell, Netlist
from kohakulayout.physics import KindCover, get, reach_cells
from kohakulayout.templates.physics.gates import GatesPowerPhysics, problem
from kohakulayout.templates.physics.gates.fields import (
    POWER_REACH,
    VDD_EMITTER,
    GatesFields,
)


def test_power_pack_needs_and_emitter() -> None:
    physics = get("gates-power@1")
    assert isinstance(physics, GatesPowerPhysics) and isinstance(
        physics.fields, KindCover
    )
    fields: GatesFields = physics.fields
    assert fields.needs(Cell(id="g", kind="AND", footprint="AND")) == ("power",)
    assert fields.needs(Cell(id="i", kind="IN", footprint="IN")) == ()
    assert fields.needs(
        Cell(id="d", kind="DFF", footprint="DFF", needs=("clock",))
    ) == ("power", "clock")
    assert fields.emitters() == (VDD_EMITTER,)
    assert "VDD" in physics.unit_footprints()
    reach = reach_cells(VDD_EMITTER, 5, 5)
    assert len(reach) == (2 * POWER_REACH + 1) ** 2 and (5 - POWER_REACH, 5) in reach
    assert physics.objective.weights["emitters"] == 1


def test_power_fixture_names_the_variant() -> None:
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/and_or_not_power.kl")
        .read_text()
    )
    netlist = Netlist.parse(text)
    prob = problem(netlist, power=True, width=24, height=12)
    assert prob.physics == "gates-power@1" and prob.check() == []
    assert problem(netlist).physics == "gates@1"
