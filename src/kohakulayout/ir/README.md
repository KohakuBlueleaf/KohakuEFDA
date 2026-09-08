# kohakulayout.ir

The levels: netlist, problem, layout, assessment, plus refusal and frame; canonical
JSON and the text form. A leaf package: imports nothing from the framework but
`errors`.

## Files

| file | what it is |
|---|---|
| `base.py` | `Model`, `Node`, `Level`, `Rate`, attrs and id checks, the digest, the level registry, the text codec hook |
| `geometry.py` | sides, rotations, port and attach cells, footprint cells, contiguity, connectivity |
| `fabric.py` | `Rect`, `Carrier`, `Region` (canonical rectangle cover), `Fabric` |
| `netlist/` | L3: shapes, hierarchy, flow order, the `Netlist` level |
| `layout.py` | L2: placements, segments, wires, units, reservations, the `Layout` level, flattening |
| `assessment.py` | L1: findings, metrics, the `Assessment` level |
| `problem.py` | a netlist bound to a fabric and a physics id; the cross-level checks |
| `refusal.py` | `Refusal` and the stage names |
| `frame.py` | the progress envelope |
| `json.py` | canonical JSON in and out, dispatched on the `level` key |
| `dump.py` | the ASCII picture, output only |
| `text/` | the `.kl` grammar, parser, assembler and writer |

## Dependencies

- `pydantic` for every shape; `lark` inside `text/`.
- `kohakulayout.errors` only.
