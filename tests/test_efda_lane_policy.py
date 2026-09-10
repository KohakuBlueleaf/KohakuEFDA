"""The project's lane policy: a join or a branch leaves a straight tree cell, never a bend, the port cell behind an attach cell counted."""

import kohakuefda.layout.router as router_rules
from kohakuefda.layout.router import LanePolicy
from kohakulayout.ir import Net, PinRef, Segment
from kohakulayout.state.router.trees import Plan


class _World:
    """A world that only knows which port cell stands behind each attach cell."""

    def __init__(self, behind: dict[tuple[int, int], tuple[int, int]]) -> None:
        self.behind = behind

    def port_choices(self, cell_id: str):
        return {
            "p": tuple(
                (f"port{i}", attach, port)
                for i, (attach, port) in enumerate(self.behind.items())
            )
        }


NET = Net(id="n", carrier="belt", sources=(PinRef(cell="c", pin="p"),))
PIPE_TREE = Net(
    id="w",
    carrier="pipe",
    sources=(PinRef(cell="s1", pin="o"), PinRef(cell="s2", pin="o")),
    sinks=(PinRef(cell="t1", pin="i"), PinRef(cell="t2", pin="i")),
)


def _origins(plan: Plan, junctions, joinable, merging: bool, behind=None, net=NET):
    return LanePolicy().origins(
        _World(behind or {}), net, plan, junctions, joinable, merging
    )


def test_bends_and_bare_ends_are_no_place_for_a_junction() -> None:
    trunk = Segment(
        carrier="belt", layer="ground", cells=((0, 0), (1, 0), (2, 0), (2, 1), (2, 2))
    )
    plan = Plan(net_id="n", segments=[trunk])
    allowed = _origins(plan, {}, frozenset(trunk.cells), merging=True)
    assert allowed == {(1, 0), (2, 1)}


def test_an_attach_cell_is_straight_only_with_its_port_cell_in_line() -> None:
    trunk = Segment(carrier="belt", layer="ground", cells=((0, 0), (1, 0), (2, 0)))
    plan = Plan(net_id="n", segments=[trunk])
    joinable = frozenset(trunk.cells)
    in_line = _origins(plan, {}, joinable, True, behind={(0, 0): (-1, 0)})
    assert (0, 0) in in_line
    at_a_bend = _origins(plan, {}, joinable, True, behind={(0, 0): (0, -1)})
    assert (0, 0) not in at_a_bend


def test_joins_stay_before_the_first_branch_and_branches_after_the_last_join() -> None:
    trunk = Segment(
        carrier="belt", layer="ground", cells=tuple((x, 0) for x in range(8))
    )
    plan = Plan(net_id="n", segments=[trunk])
    junctions = {(2, 0): "merge", (5, 0): "split"}
    joinable = frozenset(trunk.cells)
    joins = _origins(plan, junctions, joinable, True, net=PIPE_TREE)
    branches = _origins(plan, junctions, joinable, False, net=PIPE_TREE)
    assert joins == frozenset((x, 0) for x in range(1, 5))
    assert branches == frozenset((x, 0) for x in range(3, 7))


def test_a_lane_of_one_own_cell_offers_no_attach_cell_as_the_engine_did(
    monkeypatch,
) -> None:
    monkeypatch.setattr(router_rules, "ATTACH_MIN_CELLS", 2)
    trunk = Segment(carrier="belt", layer="ground", cells=((0, 0), (0, 1), (0, 2)))
    short = Segment(carrier="belt", layer="ground", cells=((1, 1), (0, 1)))
    plan = Plan(net_id="n", segments=[trunk, short])
    joinable = frozenset(trunk.cells) | frozenset(short.cells)
    behind = {(0, 0): (0, -1), (1, 1): (2, 1)}
    allowed = _origins(plan, {(0, 1): "merge"}, joinable, True, behind=behind)
    assert (1, 1) not in allowed
    longer = Segment(carrier="belt", layer="ground", cells=((2, 1), (1, 1), (0, 1)))
    plan = Plan(net_id="n", segments=[trunk, longer])
    joinable = frozenset(trunk.cells) | frozenset(longer.cells)
    behind = {(0, 0): (0, -1), (2, 1): (3, 1)}
    allowed = _origins(plan, {(0, 1): "merge"}, joinable, True, behind=behind)
    assert {(2, 1), (1, 1)} <= allowed


def test_a_belt_lane_may_attach_on_any_straight_cell() -> None:
    trunk = Segment(
        carrier="belt", layer="ground", cells=tuple((x, 0) for x in range(8))
    )
    plan = Plan(net_id="n", segments=[trunk])
    junctions = {(2, 0): "merge", (5, 0): "split"}
    joinable = frozenset(trunk.cells)
    straight = frozenset((x, 0) for x in range(1, 7))
    assert _origins(plan, junctions, joinable, True) == straight
    assert _origins(plan, junctions, joinable, False) == straight


class _Placed:
    def __init__(self, placed: set[str]) -> None:
        self.placements = {c: None for c in placed}


def _terminal(cell: str, pin: str, direction: str, attach):
    from kohakulayout.state.router.protocol import Terminal

    return Terminal(
        ref=PinRef(cell=cell, pin=pin),
        cell=attach,
        layer="ground",
        carrier="belt",
        direction=direction,
        options=((pin, attach),),
        bound=True,
    )


def test_a_pin_waits_for_its_lane_partner_as_the_engine_did() -> None:
    from kohakuefda.physics.facts import lane_fact

    net = Net(
        id="m",
        carrier="belt",
        sources=(PinRef(cell="g", pin="o0"), PinRef(cell="g", pin="o1")),
        sinks=(PinRef(cell="t1", pin="i"), PinRef(cell="t2", pin="i")),
        attrs={
            "endfield": {
                "lanes": [
                    lane_fact(("g", "o0"), ("t1", "i"), 1),
                    lane_fact(("g", "o1"), ("t2", "i"), 1),
                ]
            }
        },
    )
    found = (
        _terminal("g", "o0", "out", (1, 0)),
        _terminal("g", "o1", "out", (2, 0)),
        _terminal("t1", "i", "in", (9, 0)),
    )
    kept = LanePolicy().pending(_Placed({"g", "t1"}), net, found, None)
    assert [str(t.ref) for t in kept] == ["g.o0", "t1.i"]
    alone = LanePolicy().pending(_Placed({"g"}), net, found[:2], None)
    assert alone == found[:2]


def test_the_trunk_runs_to_the_fullest_then_farthest_sink_as_the_engine_did() -> None:
    from kohakuefda.physics.facts import lane_fact

    net = Net(
        id="m",
        carrier="belt",
        sources=(PinRef(cell="s", pin="o"),),
        sinks=(PinRef(cell="near", pin="i"), PinRef(cell="far", pin="i")),
        attrs={
            "endfield": {
                "lanes": [
                    lane_fact(("s", "o"), ("near", "i"), 1),
                    lane_fact(("s", "o"), ("far", "i"), 1),
                ]
            }
        },
    )
    root = _terminal("s", "o", "out", (0, 0))
    near = (frozenset({(3, 0)}), _terminal("near", "i", "in", (3, 0)))
    far = (frozenset({(9, 0)}), _terminal("far", "i", "in", (9, 0)))
    assert LanePolicy().trunk(None, net, root, [near, far]) == [far]
    heavier = net.model_copy(
        update={
            "attrs": {
                "endfield": {
                    "lanes": [
                        lane_fact(("s", "o"), ("near", "i"), 2),
                        lane_fact(("s", "o"), ("far", "i"), 1),
                    ]
                }
            }
        }
    )
    assert LanePolicy().trunk(None, heavier, root, [near, far]) == [near]


def test_the_tree_grows_from_the_source_of_the_engines_first_lane() -> None:
    from kohakuefda.physics.facts import lane_fact

    net = Net(
        id="m",
        carrier="belt",
        sources=(PinRef(cell="s", pin="o0"), PinRef(cell="s", pin="o1")),
        sinks=(PinRef(cell="t", pin="i"),),
        attrs={
            "endfield": {
                "lanes": [
                    lane_fact(("s", "o0"), ("t", "i"), 1),
                    lane_fact(("s", "o1"), ("t", "i"), 5),
                ]
            }
        },
    )
    world = _Placed({"s", "t"})
    world.attach_cell = lambda cell, pin: (9, 0)
    first = _terminal("s", "o0", "out", (0, 0))
    second = _terminal("s", "o1", "out", (1, 0))
    assert LanePolicy().root(world, net, [first, second]) is second
