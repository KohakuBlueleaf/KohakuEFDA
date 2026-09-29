# solvers/lines

The community's line shape (game-knowledge PLC-09 to PLC-13) as the starting layout of
`endfield.guided` (`seed_kind="lines"`): rows by depth from the Depot Bus, groups packed
against the bus faces, the whole structure placed in one batch and legalised with its
lanes reserved.

## Files

| File | Description |
|---|---|
| `seed.py` | `EndfieldLines` (`initial`: rows by depth, sorted under their partners, loops tuned, wide rows folded; `variants`: the lane caps of `LANE_TRIES`; `laid`: boxes, group frames, lane strips, bus parts and rotations; `channels`: lane strips and `SIDE_CHANNEL` columns per carrier; `decode`: one `place_batch`), `lines_seed` (the variants legalised within a local action budget) |
| `graph.py` | `LineGraph`: parts, bricks, machines and side cells, `links`/`feeds` from the lane facts, loops (`condensed`, `regions`), groups (`clusters`, `absorbed` below `SMALL_GROUP`), port columns, `stacks` and `span` of side cells; `partners` |
| `depths.py` | `LineDepths`: each item's row and turn (`rows_for`: bricks seed row 0, pipe bands facing the bus, chained and terminal items along their maker's row, `merge_rows` for sparse rows), `mirrored` pipe bands |
| `order.py` | `LineOrder`: `reorder` (each row under its partners' ports, both sweeps), `ends` and `guests` |
| `rows.py` | `LinesRows.group_layout`: rows packed over their partners' ports (`pack` with pockets every `POCKET_SPAN`, `targets`, `blocked` loops), lane widths (`bands`), far bricks outside the aligned run |
| `shape.py` | `LinesShape`: bus faces (`line_faces`), width budgets (`budgets`), `fold`; `room_of` |
| `pack.py` | `pack_groups`: groups against the bus faces, the rest by a bounded corner search (`NODES`) for the smallest box plus trunk length |

## Dependencies

- `kohakuefda.physics` (`boundaries`, `fabric`, `facts`).
- `kohakulayout` (`structural.floorplan` sizes and items, `structural.legalize`, `state.attach`, `ir`).
