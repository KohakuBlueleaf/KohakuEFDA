# layout/

The board, the stage's settings and solver table, the router, the stages and the
pipeline. The layout stage is a consumer of KohakuLayout: it turns
the netlist into a framework problem (`synth/`), runs the solver the project name maps
to (the project's own in `solvers/` for `regional`, `hc` and `sa`; the framework's
`baseline` and `inorder`), and translates the layout back. The default stage runs `hc`
(`endfield.climb`) on the `auto` kernel for 600 seconds with seed 0; `seconds` and
`max_actions` both at 0 stop after `DEFAULT_UNITS` charged actions.

## Files

| File | Description |
|---|---|
| `board.py` | Basement, ring, fixed cells, slots and independently retained entry border |
| `router.py` | `EndfieldRouter`: the framework's lane router (`lane_order` `wide` lays the wider span first, `near` the shorter, for drops before returns, `sides` the shorter with every lane arriving from beside its sink (`from_aside`: the pins' attach cells share no column and no row) before the drops onto it, so a run takes the port at its end and the drops the rest; `wire_model` `lanes`, a bundle of lanes per net; `tree` keeps one tree per net) with the project's lane order for the nets a placement touches (pipes first; a pipe tree with several sources and sinks by role, trunk, join, branch; under `FAN_TREES` (off) a belt tree from one source to several sinks waits until every sink stands and runs its trunk to the farthest, `fans_out`; a pipe tree from several machines (not conduit outlets) waits until every source stands and grows from the farthest so the nearer ones find a straight cell to join, `fans_in`; every other lane plain; then the lane's rate, then its span, from the net's lane facts through `lanes_at` and `tree_lane`) and its `LanePolicy`, on by default (`ROUTER_NEGOTIATION` in `engine.py`): a pin is reached once a lane of its has both ends placed (`pending`), the tree grows from the source of the first lane (`root`) and the trunk runs to the fullest, then farthest, placed sink (`trunk`; a pipe tree's fullest sink when placed), a junction only on a straight cell of the standing lanes with the port cell behind an attach cell counted (`port_cells_behind`) and only on a lane that laid `ATTACH_MIN_CELLS` cells of its own (`laid_enough`), and on a pipe tree a join before the trunk's first branch and a branch after its last join (the trunk named by the plan's lanes, `trunk_index`, a junction at a trunk end that is no port cell, or that a lane laid earlier covers, being the trunk's own); `LanePolicy.lanes` names a net's lanes in laying order and `rank` their order across nets (`lane_key`: pipes first, then the role, the higher rate, the wider span between the pins' designated attach cells, `span_of` over `designated_cell`, the first port choice whichever port the wire took; `tree_ends`); `blockers` names a pipe trunk's other attachments for a join or branch with nowhere to attach; `JOIN_ONLY_LANES` off allows a one-cell lane only port to port, never as a split or a merge alone, and such a lane searches a path without that cell; `lane_ends` gives a solver the cells the router would open on one pin's standing lanes |
| `settings.py` | `settings_of` (overrides typed by their defaults, unknown names refused), the stage's flat settings, the project's solver names over its own solvers and the framework's, typed solver options, the router's settings (`ROUTER_COSTS`: a ten-times scale, step 10, turn 5, bridge 40, a displaced cell 20, and the detour rule; `ROUTER_NEGOTIATION`: no rip-up at placement time, the lane bundle, single-float cost sums), the budget, the studio's catalogue (`Entry`, `Catalog`), `ConfigurationError` |
| `stages.py` | Four stage APIs; the layout stage runs the framework on the synth's problem and translates the layout back |
| `tiles.py`      | `lay_out_tile(hier, module, seeds, units)`: the unit's problem on a growing box (`tile_box`, `pinned_extent`) solved with `hc` over seeds inside a time cap, the best complete and valid layout by the pack's cost (`cost_of`) kept as a `TileResult` with its macro; `lay_out_tiles` for every module; `tile_complexity`, `text_map`; `tile_box` starts from stage rows, or from a square of `SQUARE` times the cells' area when the rows would be taller than wide (a loop or a fan is a mesh, not a column) |
| `pipeline.py` | Scenario-to-artifacts orchestration and recorded frames |

## Dependencies

- `model`, `plan` (`depot`, `netlist`, `planner`), `synth`, `solvers`, `flow`, `verify`, `kohakulayout` (`engine`, `pipeline`, `solvers`).
