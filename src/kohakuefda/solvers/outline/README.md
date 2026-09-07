# outline/

Experimental `hc-outline` and `sa-outline` strategies: construct a complete routed
factory in a temporary larger workspace, then search against the original outline.
The scenario, netlist, supplies, fixed depot cells/slots and original fluid-entry
border remain unchanged. Placement and routing remain atomic and coupled.

## Files

| File | Provides |
|---|---|
| `__init__.py` | Validated settings, bounded workspace expansion and HC/SA variants |
| `search.py` | Complete routed overflow-minimization trajectory and target stop gate |
| `moves.py` | Inward relocation, target infill, coordinated cuts and shared local repair |

## Settings and outcomes

Shared HC/SA settings retain their meanings. Additional settings:

| Setting | Default | Meaning |
|---|---|---|
| `workspace_extra` | 20 | Additional width and height of initial search area |
| `workspace_growth` | 20 | Additional width/height per expansion |
| `workspace_max_extra` | 60 | Maximum extra extent; at most 256 |
| `workspace_steps` | 48 | Construction proposals per extent, capped by `construction_steps` |
| `outline_radius` | 6 | Target-directed local relocation radius |

Workspace growth extends east/south without moving the original coordinate origin,
fixed slots or entry borders. Each expansion preserves the previous best partial
physical realization and reassesses it. All contexts share the same action/time
budget. More room is not a guarantee of routability. A zero construction or
improvement phase cap still disables that phase; without global limits the search
is finite. A routed seed supplied to the solver must be a target-valid snapshot.

After construction, every accepted workspace state remains complete and physically
routed. Search prioritizes target overflow distance, then occupied area and wire
length. Ordinary compaction/repacking is augmented by inward and global infill
moves. The workspace remains available for uphill SA rearrangements; it is not cut
off after each improvement. Plain pipes may use the original legal ring without
penalty, but pipes beyond the original routing grid are overflow. Production and
belt overflow do not disappear through occupied-area clipping.

A workspace snapshot uses a separate backend domain. Parent `best_routed` and
`best_verified` never receive oversized evidence. Parent diagnostics explicitly
carry `layout.workspace_only`, `workspace_routed`, workspace dimensions and target
violation metrics. When all anchors fit, bounded coupled reconstruction may reroute
on the real board; zero-overflow realizations can be re-imported and reassessed.
Only complete physical target-board validation publishes a solution. No rate check
is implied. Studio displays oversized completion as target-incomplete.

Use `seconds` for the total budget, including initial construction, expansion,
compaction and target projection. Example solver options for a closer initial
workspace: `{"workspace_extra":10,"workspace_growth":10,"workspace_steps":128}`.
These are experimental settings, not a claim of universal improvement.

## Dependencies

- `framework.workspace`: isolated workspaces, metrics and target publication.
- `local`: HC/SA acceptance, construction, trajectories and physical moves.
- `regional`: anchor proposals. No planning or logical-net changes.
- External: `numpy` for target infill ranking.
