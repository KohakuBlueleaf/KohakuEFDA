# kohakulayout.templates.physics.gates

The first instance: logic gates on a grid, wired like a schematic. It exercises every
stage of the protocol except flow and is deliberately unlike any factory game.

| file | what |
|---|---|
| `__init__.py` | `GatesPhysics` (id `gates`), `GatesPowerPhysics` (id `gates-power`: every gate needs `power`), both version `1` and registered; `problem(netlist, power=False, **params)` |
| `fields.py` | `GatesFields` on `KindCover` with the `VDD` emitter (kind `power`, square reach of radius 3, overlap allowed); `needs` for gate footprints |
| `fabric.py` | `fabric(params)`: W×H from params, layers `ground` and `overhead`, carriers `wire` and `clk`, region `build`, entries W and E |
| `library.py` | `LIBRARY`: AND, OR, XOR 3×3; NOT, BUF 2×3; DFF 3×4 with `clk` on the south; IN, OUT 1×1. `JUMPER` unit, `VDD` emitter, `FANOUT_LIMIT` |
| `carriers.py` | `GatesCarriers`: carriers share cells across layers, wires cross through a jumper, clk never crosses clk, junctions free, jumpers transfer wires |
| `boundaries.py` | `GatesBoundaries`: constraint `edge` with `attrs["gates"]["side"]` anchors on that edge; `legal` refuses an edge cell off its edge |
| `rules.py` | `gates.edge` and `gates.fanout`, as `FunctionRule`s |
| `objective.py` | `GatesObjective`: area, wire cells, jumpers, emitters |
| `synth.py` | `from_expressions` (`y = a & b | ~c`) and `random_circuit(seed, ...)` |
| `fixtures/` | `.kl` problems written by hand |

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`, `kohakulayout.physics`.
