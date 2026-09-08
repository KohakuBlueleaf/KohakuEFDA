# kohakulayout.ir.netlist

L3: what must exist and how it must connect.

## Files

| file | what it is |
|---|---|
| `model.py` | `Port`, `Footprint`, `Pin`, `Constraint`, `Cell`, `PinRef`, `Net`, `Group` |
| `hier.py` | `ModulePort`, `Module`, `Macro`, and `derive_footprint` for a macro's fragment |
| `order.py` | producer-before-consumer order with the back edges of loops |
| `__init__.py` | the `Netlist` level: lookups, checks, `flatten`, `flow_order`, fan-in and fan-out |

## Dependencies

- `kohakulayout.ir.base`, `geometry`, `layout` (a macro carries a layout fragment).
