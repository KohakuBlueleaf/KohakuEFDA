# route/

The two-layer occupancy grid (0 ground, 1 sky) every rule reads: claims, conflicts
and lookups over a project layout. Routing itself is KohakuLayout's; the synth
translates its wires into the project's segments and units.

## Files

| File      | Description                                                                                          |
| --------- | ---------------------------------------------------------------------------------------------------- |
| `grid.py` | `Occupancy` (claims, conflicts, lookups; outside inputs claim the sky of their cell) and `occupancy_of` |

## Dependencies

- `kohakuefda.model`, `kohakuefda.layout` (`geometry`)
