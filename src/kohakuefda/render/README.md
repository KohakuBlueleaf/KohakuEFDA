# render/

Every human-facing view of the machine artifacts: rich tables for plans and
netlists (targets, machines, balances, nets, cells, findings), the text grid
and the PNG of a layout. The viewer bundle is served from `web_dist/` by the
CLI.

## Files

| File           | Description                                                             |
| -------------- | ----------------------------------------------------------------------- |
| `tables.py`    | `plan_report`, `netlist_report` and their per-section tables, `findings_table`, `SEVERITY_STYLE` |
| `grid_text.py` | `render_text`: one character per cell (machine initial, belt arrows, pipe bars, unit glyphs) |
| `png.py`       | `render_png`: matplotlib drawing of footprints, segments and ports (optional dependency) |

## Dependencies

- `kohakuefda.model`, `kohakuefda.layout`
- External: `rich`; `matplotlib` for PNG (extra `viz`)
