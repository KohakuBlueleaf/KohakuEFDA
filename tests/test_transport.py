"""Exact operating points, compatible direct lanes and reconstruction boundaries."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.operating import (
    OperatingPointError,
    operating_points,
    packed_rates,
)
from kohakuefda.plan.planner import plan
from kohakuefda.plan.transport import TransportError, allocate, materialize
from kohakuefda.plan.transport.domains import match_ports, unions
from kohakuefda.synth import problem_of

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"


@pytest.fixture(scope="module")
def allocated():
    dataset = Dataset.load(DATASET)
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_dense_valley6.toml")
    planned = plan(dataset, scenario)
    netlist = build_netlist(dataset, scenario, planned, "rated")
    result = allocate(dataset, netlist, seconds=5)
    assert result.feasible, result.reason
    return dataset, netlist, result


def test_machine_activity_and_lane_capacity_are_conserved() -> None:
    assert operating_points(Fraction(10, 3), 4) == (1, 1, 1, Fraction(1, 3))
    assert packed_rates(Fraction(75), Fraction(30)) == (30, 30, 15)
    assert operating_points(0, 2) == (0, 0)
    assert packed_rates(0, 30) == ()
    for activity, count in ((-1, 1), (2, 1), (0, -1)):
        with pytest.raises(OperatingPointError):
            operating_points(activity, count)
    with pytest.raises(OperatingPointError):
        packed_rates(1, 0)


def test_port_matching_accounts_for_competing_ingredient_domains() -> None:
    domains = [(0, 1), (0,), (1, 2)]
    selected = match_ports(domains)
    assert len(set(selected)) == 3
    assert all(port in allowed for port, allowed in zip(selected, domains, strict=True))
    with pytest.raises(TransportError):
        match_ports([(0,), (0,), (1, 2)])
    assert unions([frozenset({0}), frozenset({1})]) == [
        frozenset({0}),
        frozenset({1}),
        frozenset({0, 1}),
    ]


def test_direct_transport_materialises_as_independent_valid_lanes(allocated) -> None:
    dataset, netlist, result = allocated
    before = netlist.model_dump_json()
    physical = materialize(dataset, netlist, result)
    assert netlist.model_dump_json() == before
    assert result.optimal and result.lanes > 0
    assert problem_of(dataset, physical).check() == []
    for net in physical.nets:
        if net.kind == "belt" and net.rate > 0:
            assert len(net.sources) == len(net.sinks) == 1
            assert net.rate <= dataset.constants.belt_per_min
            assert net.sources[0].rate == net.sinks[0].rate == net.rate
    for cell in physical.cells:
        for direction in ("in", "out"):
            ports = [
                (p.cell, p.edge)
                for p in cell.pins
                if p.kind == "belt" and p.direction == direction
            ]
            assert len(ports) == len(set(ports))


def test_recycled_water_does_not_become_extra_external_supply() -> None:
    dataset = Dataset.load(DATASET)
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_dense_wuling6.toml")
    planned = plan(dataset, scenario)
    netlist = build_netlist(dataset, scenario, planned, "rated")
    item = "item_liquid_water"
    outside = sum(
        (
            pin.rate
            for cell in netlist.cells
            if cell.kind == "outlet" and cell.machines[0].config.get("item") == item
            for pin in cell.pins
        ),
        Fraction(0),
    )
    assert planned.items[item].produced == 12
    assert outside == planned.items[item].supplied == 150
    cells = {cell.id: cell for cell in netlist.cells}
    for net in netlist.nets:
        for source in net.sources:
            pin = next(p for p in cells[source.cell_id].pins if p.id == source.pin_id)
            assert source.rate == pin.rate, net.id


def test_the_direct_policy_is_the_rated_netlist_materialised(allocated) -> None:
    dataset, netlist, result = allocated
    scenario = netlist.scenario
    direct = build_netlist(dataset, scenario, plan(dataset, scenario), "direct")
    expected = materialize(dataset, netlist, result)
    assert direct.model_dump_json() == expected.model_dump_json()
    with pytest.raises(ValueError, match="transport"):
        build_netlist(dataset, scenario, plan(dataset, scenario), "teleport")


def test_allocation_cannot_be_applied_to_a_changed_input(allocated) -> None:
    dataset, netlist, result = allocated
    changed = netlist.model_copy(deep=True)
    changed.dataset_version += "-changed"
    with pytest.raises(TransportError, match="different source"):
        materialize(dataset, changed, result)
