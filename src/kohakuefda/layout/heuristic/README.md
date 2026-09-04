# layout/heuristic/

A search over placements, beside the constructive spread rather than instead of
it. The state is anchors and rotations only — no grid, no wires, no routing —
which is what makes a move cheap: a move touches one or two blocks, so only the
nets on those blocks change length and the rest of the cost is a sweep over a
few dozen rectangles.

`Engine.contend` runs this on a fresh `Site` seeded from the constructive
layout and keeps whichever answer is smaller, so a search that comes out worse,
or does not come out whole at all, cannot make the result worse than the spread.

## The cost

`recompute` rebuilds every term from the anchors and is the oracle the
incremental `put` is held to; `tests/test_heuristic.py` holds `put` to it and
the Rust mirror to both.

| Term | What it counts |
|---|---|
| `area` | The rectangle the anchors need |
| `wire` | Span between each net's two pins, a lower bound on the routed path |
| `overlap` | Cells two footprints share, with the free cell a wired port is owed |
| `group` | Group rules unmet: a brick off its bus face, a machine outside its zone |
| `shut` | Cells of one block's lane corridor another stands on |
| `crowd` | Heat left where a lane failed to find a path, fed back from the router |
| `jam` | Lane demand a bin has no free floor for |
| `tight` | Floor kept back for lanes: `wire * route_slack` above the machine floor |

Terms are normalised to the placement the walk starts at, so a schedule tuned on
one factory means something on another.

`jam` is a Rent-style congestion estimate: each net spreads `(w + h) / (w * h)`
per cell over its bounding box into 4-cell bins, each footprint claims floor
from the bins it covers, and the term is the demand beyond the free floor,
summed. It is **off by default** (`w_jam = 0`). It does what it is for — with it
raised, the largest bundled factory goes from a search whose answer the site
refuses to one that builds — but on every bundled factory it buys that
routability with more area than it saves: at the lowest weight that builds, that
factory comes out at 1155 cells against the spread's 1089, and the two factories
the search otherwise wins fall back to the spread's answer. Raise it for a line
the router cannot serve at all, not to make a layout smaller.

## Files

| File | Holds |
|---|---|
| `state.py`    | `Weights`, `Terms`, `Scale`, `Placement`: the anchors, the cost, `put` (one block moved, cost folded forward), `swap`, `recompute` (the oracle), `room`, `warm`/`cool` (the heat map), the congestion bins |
| `moves.py`    | `Moves`: VPR's set — displace within a shrinking range, swap, rotate — plus a macro shift; `narrow`, `propose`, `undo` (another move, so nothing is copied) |
| `schedule.py` | `SCHEDULES`: `Geometric`, `FastSA`, `Adaptive`; `first_temperature` measured from the walk's own uphill moves |
| `anneal.py`   | `Annealer`: `calibrate`, `run`, `polish` (overlap priced out, only improvements taken), `separate` (overlapping pairs pushed apart until none are left), `Trace` |
| `genetic.py`  | `Evolver`: a population of placements, spatial crossover, memetic local search |
| `seed.py`     | `start`: where a walk begins — `construct`, `scatter`, `best-of`, `refine`; `held`, `pinned`, `scatter` |
| `engine.py`   | `run` (sweep the lane reserves, keep the best built), `attempt`, `materialise` (every block down, then the whole netlist routed at once), `repair` (the router as judge), `ends`, `offers`, `build`, `scorch`, `crowded` |
| `native.py`   | `NATIVE`, `build`, `send`, `receive`, `anneal`: the whole state over to Rust once, so nothing crosses the boundary per move |

## Dependencies

- `kohakuefda.layout.site`, `kohakuefda.layout.spread`, `kohakuefda.model`
- Optional: `kohakuefda._native` (the Rust mirror in `src/kohakuefda-rs/heuristic/`)
