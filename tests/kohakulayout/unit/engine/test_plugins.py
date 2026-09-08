"""The plugin chain and its built-in occupants."""

from kohakulayout.engine import Context
from kohakulayout.engine.plugins import (
    DROP,
    REPACK,
    AreaBound,
    BudgetPlugin,
    CheckpointPlugin,
    DedupPlugin,
    EnginePlugin,
    FrameSampler,
    MissingCount,
    PluginManager,
    RepackPlugin,
    ScreenPlugin,
    default_plugins,
)
from kohakulayout.templates.physics.null import problem


class Tag(EnginePlugin):
    def __init__(self, name: str, priority: int) -> None:
        self.name, self.priority = name, priority

    def on_frame(self, ctx, frame):
        return frame.model_copy(
            update={
                "attrs": {
                    "tags": {
                        "seen": [
                            *frame.attrs.get("tags", {}).get("seen", []),
                            self.name,
                        ]
                    }
                }
            }
        )


class Dropper(EnginePlugin):
    name, priority = "dropper", 15

    def on_frame(self, ctx, frame):
        return DROP


def test_manager_orders_by_priority_and_honours_drop() -> None:
    manager = PluginManager((Tag("late", 90), Tag("early", 10)))
    assert manager.names() == ("early", "late")
    ctx = Context(problem(), router=None, plugins=(Tag("late", 90), Tag("early", 10)))
    frame = ctx.frame("x")
    assert frame.attrs["tags"]["seen"] == ["early", "late"]
    ctx = Context(problem(), router=None, plugins=(Dropper(), Tag("late", 90)))
    assert ctx.frame("x") is None
    assert [p.name for p in default_plugins()] == ["budget", "sampler", "dedup"]


def test_screens_dedup_repack_checkpoint_and_budget() -> None:
    calls = []
    REPACK["count"] = lambda builder: calls.append(len(builder.placements))
    screen = ScreenPlugin((AreaBound(4), MissingCount(3)))
    dedup, repack, checkpoint = (
        DedupPlugin(),
        RepackPlugin(every=1, action="count"),
        CheckpointPlugin(every_accepts=2),
    )
    ctx = Context(
        problem(),
        router=None,
        plugins=(BudgetPlugin(), screen, dedup, repack, checkpoint),
    )
    result = ctx.attempt(lambda b: b.place("box", (0, 0)), cost=3)
    assert result.ok and ctx.budget.used == 4
    assert ctx.consider() is not None and calls == [1]
    ctx.attempt(lambda b: b.place("c", (7, 7)))
    assert ctx.consider() is None and screen.rejected == 1 and calls == [1]
    ctx.attempt(lambda b: b.withdraw("c"))
    first = ctx.assess()
    assert ctx.assess() is first and dedup.hits == 2
    assert ctx.consider() is first and calls == [1]
    assert ctx.accept() is not None and calls == [1, 1] and len(ctx.checkpoints) == 1
    assert FrameSampler(every=3).on_frame(ctx, ctx.frame("start")) is None
    del REPACK["count"]
