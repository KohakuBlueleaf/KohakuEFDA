# verify/

The verify stage's checks and the report. A project layout is read back as a framework
problem and layout by the synth's reverse translation, loaded into a world and judged by
KohakuLayout's verify runner under the Endfield pack; the rate rule reads the evaluation
against the plan; `flow/stability.py` judges plans. The report is the machine artifact;
the CLI renders it.

## Files

| File                | Description                                                                 |
| ------------------- | --------------------------------------------------------------------------- |
| `report.py`         | `Report`: findings, verdict, save/load                                      |
| `layout.py`         | `check_layout(dataset, layout)`: the reverse translation loaded into a world, the framework runner's findings with the project's ids put back |
| `evaluate.py`       | `evaluate(dataset, layout)`: the reverse translation under the framework's routed evaluator and the pack's flow hooks, read back as the project's `Evaluation` (rates per segment and direct link, utilisation and stall per machine) |
| `rules/rates.py`    | `rate_findings` over an evaluation: convergence, crafters below utilisation 1, idle sources |

## Rule ids

The framework's: `kl.geometry` (a placement off the grid or on another, a wire off its
pins or not one contiguous tree), `kl.occupancy` (two occupants on one cell of one layer
the pack does not let share), `kl.legal` (a placement the pack's boundaries refuse: outside
the Core AIC Area, an outside input off the border, a brick off its slot or unseated, a
bus part off the cluster, a machine outside its gas zone), `kl.missing`, `kl.unrouted`,
`kl.field` (a powered machine no pylon's square touches). The pack's: `endfield.area`,
`endfield.belt_ring`, `endfield.run_length`, `endfield.pipe_units`, `endfield.bus`,
`endfield.zone`, `endfield.core`, `endfield.conduit`, `endfield.wiring`. The rate rule:
`flow.unconverged`, `flow.starved`, `flow.idle` (warning). The netlist stage adds
`netlist.*` and the board `layout.square_unknown`.

## Dependencies

- `kohakuefda.model`, `kohakuefda.synth` (`reverse`), `kohakuefda.physics` (`flow`), `kohakuefda.flow`, `kohakulayout` (`engine`, `flow`, `verify`)
