# kohakulayout.ir.text

The hand-writable text form of every level, beside the canonical JSON.

## Files

| file | what it is |
|---|---|
| `kl.lark` | the grammar, LALR(1) with a contextual lexer, with its design comments |
| `parser.py` | the lazy parser and `parse_text` |
| `transformer.py` | parse tree to statement records |
| `assemble.py` | statement records to levels: `Levels`, fabric, netlist scopes, layout, assessment |
| `moves.py` | wire paths as moves, cells and waypoints, and back |
| `values.py` | typing the value tokens and writing values |
| `writer.py` | levels to canonical text |

## Dependencies

- `lark`; `kohakulayout.ir.*`. Registers itself as the level codec on import.
