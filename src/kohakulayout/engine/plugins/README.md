# kohakulayout.engine.plugins

Cross-cutting policy at the engine's hooks. Hooks run linearly by priority; `None`
means unchanged, `DROP` discards a frame, `False` from `pre_assess` or `pre_accept` vetoes.

| file | what |
|---|---|
| `protocol.py` | `EnginePlugin` with every hook returning None: `pre_attempt`, `post_attempt`, `pre_assess`, `post_assess`, `pre_accept`, `post_accept`, `on_frame`, `on_checkpoint`, `on_budget` |
| `manager.py` | `PluginManager`: `transform`, `first`, `notify` |
| `budget.py` | `BudgetPlugin`: charges an attempt's cost before it runs |
| `sampler.py` | `FrameSampler(every, layout_every)`: frame cadence; start, end, constructed and checkpoint frames always pass |
| `screen.py` | `ScreenPlugin(screens)` with the `SCREENS` registry: `AreaBound`, `MissingCount` |
| `dedup.py` | `DedupPlugin`: assessments cached by layout digest |
| `repack.py` | `RepackPlugin(every, action)` with the `REPACK` registry; `identity` by default |
| `checkpoint.py` | `CheckpointPlugin(every_accepts, every_seconds)` |

`default_plugins()` is budget, sampler and dedup.
