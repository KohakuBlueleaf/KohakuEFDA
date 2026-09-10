"""A pack may let a wire cross another on a cell where that wire bends (``CrossingRule.bent``); the default refuses it, in both kernels."""

import pytest

from kohakulayout._rust import HAS_RUST
from kohakulayout.physics import CrossingRule
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.templates.physics.gates import GatesPhysics
from kohakulayout.templates.physics.gates.carriers import GatesCarriers
from kohakulayout.templates.physics.gates.library import JUMPER
from tests.kohakulayout.unit.state.router.test_terminal_crossing import (
    _anchor,
    _problem,
)

KERNELS = ("python", "native") if HAS_RUST else ("python",)


class BentCrossings(GatesCarriers):
    def crossing(self, a: str, b: str) -> CrossingRule:
        return CrossingRule(mode="unit", unit=JUMPER, bent=True)


def _bend(world: World) -> tuple[int, int]:
    """A cell of the first wire whose neighbours on its run do not line up."""
    for seg in world.wires["first"].segments:
        cells = list(seg.cells)
        for i in range(1, len(cells) - 1):
            a, b = cells[i - 1], cells[i + 1]
            if a[0] != b[0] and a[1] != b[1]:
                return cells[i]
    raise AssertionError("the first wire runs straight")


def _world(kernel: str, bent: bool) -> tuple[World, StateCheck]:
    physics = GatesPhysics()
    if bent:
        physics.carriers = BentCrossings()
    world = World(_problem(), physics, kernel=kernel, router=DefaultRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("a", 0, 4) is None
        assert world.place("o0", 11, 1) is None
        tx.commit()
    return world, check


@pytest.mark.parametrize("kernel", KERNELS)
def test_a_bend_takes_no_crossing_by_default(kernel: str) -> None:
    world, check = _world(kernel, bent=False)
    bend = _bend(world)
    anchor = _anchor(world, "b", bend, (bend[0], bend[1] + 1))
    with world.transaction() as tx:
        refused = world.place("b", *anchor)
        tx.commit()
    assert refused is not None
    assert check.failures == []


@pytest.mark.parametrize("kernel", KERNELS)
def test_a_bent_rule_crosses_on_the_bend_with_the_unit(kernel: str) -> None:
    world, check = _world(kernel, bent=True)
    bend = _bend(world)
    with world.transaction() as tx:
        assert (
            world.place("b", *_anchor(world, "b", bend, (bend[0], bend[1] + 1))) is None
        )
        assert (
            world.place("o1", *_anchor(world, "o1", (bend[0], 0), (bend[0] + 1, 0)))
            is None
        )
        tx.commit()
    holders = set(world.kernel.holders_at("ground", bend))
    assert {"wire:first", "wire:second"} <= holders
    assert any(h.startswith("unit:") for h in holders)
    assert check.failures == []
