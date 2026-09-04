"""The heuristic placer's cost: the incremental fold held to the oracle that rebuilds it, and
the native mirror held to the Python reference."""

import random
from pathlib import Path

import pytest

from kohakuefda.layout.board import board_of
from kohakuefda.layout.heuristic import native
from kohakuefda.layout.heuristic.seed import start
from kohakuefda.layout.heuristic.state import Placement, Weights
from kohakuefda.layout.site import Site
from kohakuefda.layout.stages import netlist_stage, params_of, plan_stage
from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario

DATASET = Path("data/1.5.3@9764758-3/dataset.json")
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCENARIOS = ("scenario_valley_battery", "scenario_wuling_hetonite")
TURNS = (0, 90, 180, 270)
_PLANNED: dict[str, tuple] = {}
# A legal start is all these need; a good one costs a search nobody here reads.
QUICK = {"seed_attempts": 40, "seed_draws": 2}


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def _netlist(dataset: Dataset, name: str) -> tuple[Scenario, Netlist]:
    """The planned netlist for one scenario, solved once however many tests ask for it."""
    if name not in _PLANNED:
        scenario = Scenario.from_toml(FIXTURES / f"{name}.toml")
        _PLANNED[name] = (
            scenario,
            netlist_stage(dataset, scenario, plan_stage(dataset, scenario)),
        )
    return _PLANNED[name]


def _state(dataset: Dataset, name: str, params: dict) -> tuple[Placement, Site]:
    scenario, netlist = _netlist(dataset, name)
    site = Site(dataset, netlist, board_of(dataset, scenario), params)
    state = Placement(site, Weights.of(params))
    state.adopt(start(site, state, params, random.Random(3), None))
    return state, site


def _wander(state: Placement, rng: random.Random) -> bool:
    """Put one movable block somewhere it may stand; False when it picked a frozen one."""
    block = rng.randrange(state.count)
    if state.frozen[block]:
        return False
    x0, y0, x1, y1 = state.room(block)
    state.put(
        block,
        rng.randint(x0, max(x0, x1 - 1)),
        rng.randint(y0, max(y0, y1 - 1)),
        rng.choice(TURNS),
    )
    return True


@pytest.mark.parametrize("name", SCENARIOS)
def test_moving_a_block_keeps_every_term_exact(dataset: Dataset, name: str) -> None:
    """``put`` folds each term forward instead of sweeping, so every one of them has to agree
    with ``recompute``, which rebuilds them all from the anchors.

    A term that drifts is worse than a term that is wrong: the walk keeps taking moves priced
    against a cost nobody else would agree with, and only the built layout shows it.
    """
    params = params_of("layout", QUICK)
    state, _ = _state(dataset, name, params)
    rng = random.Random(11)
    for _ in range(200):
        if not _wander(state, rng):
            continue
        oracle = state.recompute()
        running = state.terms
        assert (running.area, running.wire) == (oracle.area, oracle.wire)
        assert (running.overlap, running.group) == (oracle.overlap, oracle.group)
        assert running.shut == oracle.shut
        assert running.crowd == pytest.approx(oracle.crowd)
        assert running.jam == pytest.approx(oracle.jam)


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_congestion_term_is_the_demand_no_bin_has_floor_for(
    dataset: Dataset, name: str
) -> None:
    """The running total is a sum of deltas, so it is held to the maps it claims to summarise:
    every bin's lane demand beyond the free floor it has, added up directly."""
    params = params_of("layout", QUICK)
    state, _ = _state(dataset, name, params)
    rng = random.Random(7)
    for _ in range(50):
        _wander(state, rng)
    direct = sum(
        max(
            0.0,
            state.demand[index] - max(0, state.bin_cells[index] - state.taken[index]),
        )
        for index in range(len(state.demand))
    )
    assert state.terms.jam == pytest.approx(direct)
    assert state.terms.jam >= 0.0


@pytest.mark.skipif(not native.NATIVE, reason="the native extension is not built")
@pytest.mark.parametrize("name", SCENARIOS)
def test_the_native_placement_prices_a_layout_as_the_reference_does(
    dataset: Dataset, name: str
) -> None:
    """The two implementations are one search, so the same anchors have to cost the same on
    both sides; a gap means the native walk is optimising something else."""
    params = params_of("layout", QUICK)
    weights = Weights.of(params)
    state, _ = _state(dataset, name, params)
    mirror = native.build(state, weights)
    assert mirror is not None
    rng = random.Random(5)
    for _ in range(100):
        if not _wander(state, rng):
            continue
        state.terms = state.recompute()
        native.send(mirror, state)
        area, wire, overlap, group, shut, crowd, jam = mirror.terms()
        assert (area, wire, overlap) == (
            state.terms.area,
            state.terms.wire,
            state.terms.overlap,
        )
        assert (group, shut) == (state.terms.group, state.terms.shut)
        assert crowd == pytest.approx(state.terms.crowd)
        assert jam == pytest.approx(state.terms.jam)
        assert mirror.cost() == pytest.approx(state.cost(), rel=1e-9)
