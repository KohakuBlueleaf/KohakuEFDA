"""The two kernels agree byte for byte: random operations, and every gates run replayed from its log."""

import random
from contextlib import contextmanager
from importlib.resources import files
from unittest.mock import patch

import pytest

from kohakulayout import _rust_bridge as bridge
from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Netlist
from kohakulayout.solvers import get
from kohakulayout.state import World, make_router
from kohakulayout.state.kernel import (
    KERNELS,
    NativeKernel,
    PyKernel,
    RecordingKernel,
    make_kernel,
    replay,
)
from kohakulayout.state.router import pathfinder, trees
from kohakulayout.templates.physics.gates import (
    GatesPhysics,
    from_expressions,
    problem,
    random_circuit,
)


def test_random_operations_agree() -> None:
    rng = random.Random(11)
    python, native = PyKernel(20, 14, ("ground", "overhead")), NativeKernel(
        20, 14, ("ground", "overhead")
    )
    holders = (
        [f"cell:c{i}" for i in range(6)]
        + [f"wire:n{i}" for i in range(6)]
        + ["unit:u1", "reserve:r1"]
    )
    for step in range(600):
        layer = rng.choice(["ground", "overhead"])
        cells = [
            (rng.randrange(20), rng.randrange(14)) for _ in range(rng.randint(1, 5))
        ]
        holder = rng.choice(holders)
        occupy = rng.random() < 0.6 or step < 20
        for kernel in (python, native):
            (kernel.occupy if occupy else kernel.free)(layer, cells, holder)
        if step % 40 == 0:
            assert python.save() == native.save()
            assert python.holders_at(layer, cells[0]) == native.holders_at(
                layer, cells[0]
            )
            assert python.free_for(layer, cells) == native.free_for(layer, cells)
            assert python.cells_of(holder) == native.cells_of(holder)
            assert python.holders_on(layer) == native.holders_on(layer)
            assert python.extent() == native.extent() and python.extent(
                layer
            ) == native.extent(layer)
            assert (python.occupancy(layer) == native.occupancy(layer)).all()
            assert (python.integral(layer) == native.integral(layer)).all()
    blob = python.save()
    other = NativeKernel(20, 14, ("ground", "overhead"))
    other.load(blob)
    assert other.save() == blob
    assert "native" in KERNELS and isinstance(
        make_kernel("auto", 4, 4, ("ground",)), NativeKernel
    )


@pytest.mark.parametrize("seed", [1, 2])
def test_gates_run_replays_into_the_native_kernel(seed: int) -> None:
    netlist = random_circuit(seed, inputs=3, gates=6)
    prob = problem(netlist, width=40, height=20)
    recorder = RecordingKernel(
        PyKernel(prob.fabric.width, prob.fabric.height, tuple(prob.fabric.layers))
    )
    world = World(prob, GatesPhysics(), kernel=recorder, router=make_router("default"))
    ctx = Context(prob, seed=seed, budget=Budget(units=4000))
    ctx.world = world
    get("inorder").run(ctx)
    native = replay(
        recorder.log,
        NativeKernel(prob.fabric.width, prob.fabric.height, tuple(prob.fabric.layers)),
    )
    assert native.save() == recorder.save()
    assert len(recorder.log) > 10


def test_a_native_world_solves_the_toy() -> None:
    prob = problem(from_expressions("y = a & b | ~c"), width=24, height=12)
    ctx = Context(prob, seed=1, budget=Budget(units=800), kernel="native")
    assert get("inorder").run(ctx) == "complete"
    assert isinstance(ctx.world.kernel, NativeKernel)
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/and_or_not.kl")
        .read_text()
    )
    assert Netlist.parse(text).digest()


@pytest.mark.parametrize("seed", [3, 4, 5])
def test_native_search_finds_what_python_finds(seed: int) -> None:
    """Every search of a whole run answers the same on both sides: cells, cost, crossings and rips."""
    netlist = random_circuit(seed, inputs=4, gates=8)
    prob = problem(netlist, width=48, height=24)
    ctx = Context(prob, seed=seed, budget=Budget(units=4000), kernel="native")
    searches: list[tuple] = []
    original = pathfinder.find

    def both(search, sources, targets, avoid=frozenset()):
        native = original(search, sources, targets, avoid)
        search.grid = None
        with _python_only():
            python = original(search, sources, targets, avoid)
        searches.append((native, python))
        return native

    with patch.object(pathfinder, "find", both), patch.object(trees, "find", both):
        get("inorder").run(ctx)
    assert len(searches) > 20
    assert [n for n, _ in searches] == [p for _, p in searches]


@contextmanager
def _python_only():
    was = bridge.BACKEND
    bridge.BACKEND = "python"
    try:
        yield
    finally:
        bridge.BACKEND = was
