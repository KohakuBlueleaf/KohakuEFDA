//! A* on one layer over the grid, with the pack's crossing, sharing and reservation rules handed in as tables.
//! A port of `state/router/pathfinder.py`: the same costs, the same order of expansion, the same answer,
//! on flat arrays with the tables laid out once per rules.

use std::cmp::Reverse;
use std::collections::{BTreeSet, BinaryHeap, HashMap};

use serde::Serialize;

use super::classify::{Cell, Entry, Search};
use super::grid::{Grid, XY};

pub use super::classify::{Prepared, Rules, Shape};

const DIRS: [XY; 4] = [(0, -1), (1, 0), (0, 1), (-1, 0)];

#[derive(Serialize)]
pub struct Found {
    pub cells: Vec<XY>,
    pub cost: i64,
    pub crossings: Vec<(XY, String, bool)>,
    pub rips: Vec<String>,
    pub displaces: Vec<String>,
}

/// A layer's cells as one search sees them, kept while the grid's generation stands.
pub struct Classified(Vec<Cell>);

/// Classify a layer for the rules once; `find` takes the result for every search that follows on the same grid state.
pub fn classify(grid: &Grid, layer: &str, prepared: &Prepared) -> Classified {
    Classified(Search::classify(grid, layer, prepared))
}

type Queued = Reverse<(u64, i64, XY, u8)>;

/// A heap key that orders like the estimate: the integer itself, or the bits of a non-negative f32 when costs accumulate as floats.
fn key_of(estimate: i64, float: Option<f32>) -> u64 {
    match float {
        Some(f) => f.to_bits() as u64,
        None => estimate as u64,
    }
}

pub fn find(
    grid: &Grid,
    sources: &[XY],
    targets: &[XY],
    avoid: &[XY],
    own: &[(i64, i64, u8)],
    prepared: &Prepared,
    classified: &Classified,
) -> Option<Found> {
    if sources.is_empty() || targets.is_empty() {
        return None;
    }
    let cells = prepared.width * prepared.height;
    let mut own_axis = vec![0u8; cells];
    for (x, y, axis) in own {
        if let Some(i) = prepared.at((*x, *y)) {
            own_axis[i] = *axis;
        }
    }
    let me = prepared.names.net_index.get(&prepared.rules.net).copied();
    let search = Search { grid, cells: &classified.0, prepared, own: &own_axis, me };
    let mut is_source = vec![false; cells];
    let mut is_target = vec![false; cells];
    let mut is_avoid = vec![false; cells];
    for xy in targets {
        if let Some(i) = prepared.at(*xy) {
            is_target[i] = true;
        }
    }
    for xy in avoid {
        if let Some(i) = prepared.at(*xy) {
            is_avoid[i] = true;
        }
    }
    let goals: BTreeSet<XY> = targets.iter().cloned().collect();
    let goals: Vec<XY> = goals.into_iter().collect();
    let step = prepared.rules.step;
    let gx0 = goals.iter().map(|g| g.0).min().unwrap_or(0);
    let gx1 = goals.iter().map(|g| g.0).max().unwrap_or(0);
    let gy0 = goals.iter().map(|g| g.1).min().unwrap_or(0);
    let gy1 = goals.iter().map(|g| g.1).max().unwrap_or(0);
    let heuristic = |cell: XY| -> i64 {
        let dx = if cell.0 < gx0 {
            gx0 - cell.0
        } else if cell.0 > gx1 {
            cell.0 - gx1
        } else {
            0
        };
        let dy = if cell.1 < gy0 {
            gy0 - cell.1
        } else if cell.1 > gy1 {
            cell.1 - gy1
        } else {
            0
        };
        step * (dx + dy)
    };
    let scale = prepared.rules.float_scale;
    let floats = scale > 0;
    let sc = scale.max(1) as f32;
    let as_f = |v: i64| -> f32 { v as f32 / sc };
    let mut best = vec![i64::MAX; cells * 5];
    let mut bestf = vec![f32::INFINITY; cells * 5];
    let mut parent = vec![u32::MAX; cells * 5];
    let mut meta: HashMap<u32, Entry> = HashMap::new();
    let mut starts_meta: HashMap<u32, Entry> = HashMap::new();
    let mut heap: BinaryHeap<Queued> = BinaryHeap::new();
    let mut counter: i64 = 0;
    let mut seen: BTreeSet<XY> = BTreeSet::new();
    for cell in sources {
        if !seen.insert(*cell) {
            continue;
        }
        let Some(i) = prepared.at(*cell) else {
            continue;
        };
        is_source[i] = true;
        best[i * 5] = 0;
        bestf[i * 5] = 0.0;
        let h = heuristic(*cell);
        let key = key_of(h, if floats { Some(as_f(h)) } else { None });
        heap.push(Reverse((key, counter, *cell, 0)));
        counter += 1;
    }
    let limit: Option<f64> = if prepared.rules.detour > 0.0 {
        let span = sources
            .iter()
            .flat_map(|a| {
                targets
                    .iter()
                    .map(move |b| (a.0 - b.0).abs() + (a.1 - b.1).abs())
            })
            .min()
            .unwrap_or(0);
        Some(prepared.rules.slack + prepared.rules.detour * span as f64)
    } else {
        None
    };
    let mut expansions = 0;
    while let Some(Reverse((estimate, _, cell, d))) = heap.pop() {
        if let Some(cap) = limit {
            let over = if floats {
                f32::from_bits(estimate as u32) > (cap / scale as f64) as f32
            } else {
                estimate as f64 > cap
            };
            if over {
                return None;
            }
        }
        let Some(ci) = prepared.at(cell) else {
            continue;
        };
        let state = ci * 5 + d as usize;
        let g = best[state];
        let gf = bestf[state];
        if is_target[ci] && d != 0 {
            let crossing = meta
                .get(&(state as u32))
                .is_some_and(|e| e.crossing.is_some());
            if prepared.rules.end_on_crossing || !crossing {
                return Some(reconstruct(state, &parent, &meta, &starts_meta, g, prepared));
            }
            continue;
        }
        expansions += 1;
        if expansions > prepared.rules.max_steps {
            return None;
        }
        let direction = if d == 0 {
            None
        } else {
            Some(DIRS[d as usize - 1])
        };
        let straight_only = direction.is_some()
            && meta
                .get(&(state as u32))
                .is_some_and(|e| e.crossing.is_some());
        let moves: &[XY] = if straight_only {
            std::slice::from_ref(&DIRS[d as usize - 1])
        } else {
            &DIRS
        };
        for mv in moves {
            let mv_index = if straight_only {
                d as usize
            } else {
                DIRS.iter().position(|m| m == mv).unwrap() + 1
            };
            if direction.is_some_and(|dd| *mv == (-dd.0, -dd.1)) {
                continue;
            }
            let nxt = (cell.0 + mv.0, cell.1 + mv.1);
            let Some(ni) = prepared.at(nxt) else {
                continue;
            };
            if is_source[ni] || is_avoid[ni] {
                continue;
            }
            let start = if d == 0 {
                match search.entry(cell, ci, Some(*mv), true) {
                    Some(e) => Some(e),
                    None => continue,
                }
            } else {
                None
            };
            let Some(step) = search.entry(nxt, ni, Some(*mv), false) else {
                continue;
            };
            let turn = match direction {
                Some(dd) if dd != *mv => prepared.rules.turn,
                _ => 0,
            };
            let extra = start.as_ref().map_or(0, |e| e.cost - prepared.rules.step);
            let cost = g + step.cost + turn + extra;
            let mut costf = 0.0f32;
            if floats {
                let mut mv_cost = as_f(step.cost);
                if turn != 0 {
                    mv_cost += as_f(turn);
                }
                costf = gf + mv_cost;
            }
            let nstate = ni * 5 + mv_index;
            let better = if floats {
                costf < bestf[nstate]
            } else {
                cost < best[nstate]
            };
            if better {
                best[nstate] = cost;
                bestf[nstate] = costf;
                parent[nstate] = state as u32;
                if step.crossing.is_some() || !step.rips.is_empty() || !step.displaces.is_empty() {
                    meta.insert(nstate as u32, step);
                } else {
                    meta.remove(&(nstate as u32));
                }
                match start {
                    Some(e)
                        if e.crossing.is_some()
                            || !e.rips.is_empty()
                            || !e.displaces.is_empty() =>
                    {
                        starts_meta.insert(nstate as u32, e);
                    }
                    _ => {
                        starts_meta.remove(&(nstate as u32));
                    }
                }
                let h = heuristic(nxt);
                let key = key_of(cost + h, if floats { Some(costf + as_f(h)) } else { None });
                heap.push(Reverse((key, counter, nxt, mv_index as u8)));
                counter += 1;
            }
        }
    }
    None
}

/// The path back from a target: its cells, the crossings and rips its steps recorded, and the start cell's own.
fn reconstruct(
    state: usize,
    parent: &[u32],
    meta: &HashMap<u32, Entry>,
    starts_meta: &HashMap<u32, Entry>,
    cost: i64,
    prepared: &Prepared,
) -> Found {
    let names = &prepared.names;
    let mut cells = Vec::new();
    let mut crossings = Vec::new();
    let mut rips = BTreeSet::new();
    let mut displaces = BTreeSet::new();
    let cell_of = |index: u32| -> XY {
        let ci = index as usize / 5;
        ((ci % prepared.width) as i64, (ci / prepared.width) as i64)
    };
    let mut current = state as u32;
    while current != u32::MAX {
        let xy = cell_of(current);
        cells.push(xy);
        if let Some(step) = meta.get(&current) {
            if let Some(c) = step.crossing {
                crossings.push((xy, names.nets[c as usize].clone(), step.reuse));
            }
            for r in &step.rips {
                rips.insert(names.nets[*r as usize].clone());
            }
            for u in &step.displaces {
                displaces.insert(names.unit_ids[*u as usize].clone());
            }
        }
        let previous = parent[current as usize];
        if let (Some(start), true) = (starts_meta.get(&current), previous != u32::MAX) {
            if let Some(c) = start.crossing {
                crossings.push((cell_of(previous), names.nets[c as usize].clone(), start.reuse));
            }
            for r in &start.rips {
                rips.insert(names.nets[*r as usize].clone());
            }
            for u in &start.displaces {
                displaces.insert(names.unit_ids[*u as usize].clone());
            }
        }
        current = previous;
    }
    cells.reverse();
    crossings.reverse();
    Found {
        cells,
        cost,
        crossings,
        rips: rips.into_iter().collect(),
        displaces: displaces.into_iter().collect(),
    }
}
