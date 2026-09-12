//! A* on one layer over the grid, with the pack's crossing, sharing and reservation rules in the
//! registered tables and one search's own in its query. A port of `state/router/pathfinder.py`:
//! the same costs, the same order of expansion, the same answer, on flat arrays with the layer
//! classified once per grid state.

use std::collections::{BTreeSet, BinaryHeap};

use serde::Serialize;

use super::classify::{Cell, Entry, Search};
use super::frontier::{bucket_unit, Buckets, Frontier, Keys, Node};
use super::grid::{Grid, XY};
use super::tables::{CarrierView, Tables};

pub use super::classify::{Query, View};

const DIRS: [XY; 4] = [(0, -1), (1, 0), (0, 1), (-1, 0)];

#[derive(Serialize)]
pub struct Found {
    pub cells: Vec<XY>,
    pub cost: i64,
    pub crossings: Vec<(XY, String, bool)>,
    pub rips: Vec<String>,
    pub displaces: Vec<String>,
}

/// A layer classified for every search, with whether each cell is empty.
pub struct Classified {
    pub(super) cells: Vec<Cell>,
    pub(super) empty: Vec<bool>,
}

impl Classified {
    pub(super) fn new(cells: Vec<Cell>) -> Classified {
        let empty = cells.iter().map(Cell::is_empty).collect();
        Classified { cells, empty }
    }

    pub(super) fn cell(&self, i: usize) -> &Cell {
        &self.cells[i]
    }

    pub(super) fn set(&mut self, i: usize, cell: Cell) {
        self.empty[i] = cell.is_empty();
        self.cells[i] = cell;
    }
}

const SOURCE: u8 = 1;
const TARGET: u8 = 2;
const AVOID: u8 = 4;
/// A state's slot when its step recorded no crossing, rip or displacement.
const EMPTY: u32 = u32::MAX;

/// One state: the search that reached it, its parent, its step records and its best costs.
#[derive(Clone, Copy)]
struct State {
    seen: u32,
    parent: u32,
    meta: u32,
    start: u32,
    best: i64,
    bestf: f32,
}

const UNSEEN: State = State {
    seen: 0,
    parent: u32::MAX,
    meta: EMPTY,
    start: EMPTY,
    best: i64::MAX,
    bestf: f32::INFINITY,
};

/// One cell's marks and the search that wrote them.
#[derive(Clone, Copy, Default)]
struct Mark {
    stamp: u32,
    flags: u8,
}

/// The arrays one search writes, kept between searches; a stamp marks what is current.
#[derive(Default)]
pub struct Scratch {
    stamp: u32,
    states: Vec<State>,
    marks: Vec<Mark>,
    own_axis: Vec<u8>,
    own_cells: Vec<usize>,
    metas: Vec<Entry>,
    starts: Vec<Entry>,
    heap: BinaryHeap<Node>,
    buckets: Buckets,
}

impl Scratch {
    fn begin(&mut self, cells: usize) {
        let states = cells * 5;
        if self.states.len() != states || self.stamp == u32::MAX {
            self.states = vec![UNSEEN; states];
            self.marks = vec![Mark::default(); cells];
            self.own_axis = vec![0; cells];
            self.own_cells.clear();
            self.stamp = 0;
        }
        for &i in &self.own_cells {
            self.own_axis[i] = 0;
        }
        self.own_cells.clear();
        self.stamp += 1;
        self.metas.clear();
        self.starts.clear();
    }

    fn mark(&mut self, cell: usize, flag: u8) {
        let stamp = self.stamp;
        let m = &mut self.marks[cell];
        if m.stamp != stamp {
            *m = Mark { stamp, flags: 0 };
        }
        m.flags |= flag;
    }

    fn flag(&self, cell: usize, flag: u8) -> bool {
        let m = self.marks[cell];
        m.stamp == self.stamp && m.flags & flag != 0
    }

    fn best(&self, state: usize) -> (i64, f32) {
        let s = &self.states[state];
        if s.seen == self.stamp {
            (s.best, s.bestf)
        } else {
            (i64::MAX, f32::INFINITY)
        }
    }

    fn reach(&mut self, state: usize, best: (i64, f32), parent: u32, meta: u32, start: u32) {
        self.states[state] =
            State { seen: self.stamp, parent, meta, start, best: best.0, bestf: best.1 };
    }

    /// The crossing, rips and displacements the step into a reached state recorded.
    fn meta(&self, state: usize) -> Option<&Entry> {
        let s = &self.states[state];
        (s.seen == self.stamp && s.meta != EMPTY).then(|| &self.metas[s.meta as usize])
    }

    /// What leaving a start cell recorded for the state after it.
    fn start(&self, state: usize) -> Option<&Entry> {
        let s = &self.states[state];
        (s.seen == self.stamp && s.start != EMPTY).then(|| &self.starts[s.start as usize])
    }

    fn parent(&self, state: usize) -> u32 {
        let s = &self.states[state];
        if s.seen == self.stamp {
            s.parent
        } else {
            u32::MAX
        }
    }
}

/// What one search reads besides its ends.
pub struct Ask<'a> {
    pub view: &'a View,
    pub carrier: &'a CarrierView,
    pub tables: &'a Tables,
    pub classified: &'a Classified,
}

pub fn find(
    grid: &Grid,
    sources: &[XY],
    targets: &[XY],
    avoid: &[XY],
    own: &[(i64, i64, u8)],
    ask: &Ask<'_>,
    scratch: &mut Scratch,
) -> Option<Found> {
    if sources.is_empty() || targets.is_empty() {
        return None;
    }
    let prepared = ask.view;
    let cells = prepared.width * prepared.height;
    if let Some(unit) = bucket_unit(&prepared.query) {
        let mut buckets = std::mem::take(&mut scratch.buckets);
        buckets.clear();
        let lent = setup(scratch, cells, own, targets, avoid, prepared);
        let outcome =
            expand(grid, sources, targets, &lent, ask, scratch, &mut buckets, Keys::Buckets(unit));
        scratch.own_axis = lent;
        scratch.buckets = buckets;
        if let Ok(found) = outcome {
            return found;
        }
    }
    let mut heap = std::mem::take(&mut scratch.heap);
    heap.clear();
    let lent = setup(scratch, cells, own, targets, avoid, prepared);
    let outcome = expand(grid, sources, targets, &lent, ask, scratch, &mut heap, Keys::Heap);
    scratch.own_axis = lent;
    scratch.heap = heap;
    outcome.unwrap_or(None)
}

/// Mark a search's owned axes, targets and avoided cells; the owned axes come back lent out.
fn setup(
    scratch: &mut Scratch,
    cells: usize,
    own: &[(i64, i64, u8)],
    targets: &[XY],
    avoid: &[XY],
    prepared: &View,
) -> Vec<u8> {
    scratch.begin(cells);
    for (x, y, axis) in own {
        if let Some(i) = prepared.at((*x, *y)) {
            scratch.own_axis[i] = *axis;
            scratch.own_cells.push(i);
        }
    }
    for xy in targets {
        if let Some(i) = prepared.at(*xy) {
            scratch.mark(i, TARGET);
        }
    }
    for xy in avoid {
        if let Some(i) = prepared.at(*xy) {
            scratch.mark(i, AVOID);
        }
    }
    std::mem::take(&mut scratch.own_axis)
}

/// The search itself; Err when a key lies past what the frontier holds.
#[allow(clippy::too_many_arguments)]
fn expand<F: Frontier>(
    grid: &Grid,
    sources: &[XY],
    targets: &[XY],
    own_axis: &[u8],
    ask: &Ask<'_>,
    scratch: &mut Scratch,
    frontier: &mut F,
    keys: Keys,
) -> Result<Option<Found>, ()> {
    let (view, carrier, tables, classified) = (ask.view, ask.carrier, ask.tables, ask.classified);
    let prepared = view;
    let search = Search {
        grid,
        cells: &classified.cells,
        empty: &classified.empty,
        view,
        carrier,
        tables,
        own: own_axis,
    };
    let goals: BTreeSet<XY> = targets.iter().cloned().collect();
    let goals: Vec<XY> = goals.into_iter().collect();
    let step = prepared.query.step;
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
    let scale = prepared.query.float_scale;
    let floats = scale > 0;
    let sc = scale.max(1) as f32;
    let as_f = |v: i64| -> f32 { v as f32 / sc };
    let width = prepared.width;
    let mut counter: u32 = 0;
    let mut seen: BTreeSet<XY> = BTreeSet::new();
    for cell in sources {
        if !seen.insert(*cell) {
            continue;
        }
        let Some(i) = prepared.at(*cell) else {
            continue;
        };
        scratch.mark(i, SOURCE);
        scratch.reach(i * 5, (0, 0.0), u32::MAX, EMPTY, EMPTY);
        let h = heuristic(*cell);
        let key = keys.key(h, if floats { Some(as_f(h)) } else { None }, scale);
        if !frontier.push(key, counter, (i * 5) as u32) {
            return Err(());
        }
        counter += 1;
    }
    let limit: Option<f64> = if prepared.query.detour > 0.0 {
        let span = sources
            .iter()
            .flat_map(|a| {
                targets
                    .iter()
                    .map(move |b| (a.0 - b.0).abs() + (a.1 - b.1).abs())
            })
            .min()
            .unwrap_or(0);
        Some(prepared.query.slack + prepared.query.detour * span as f64)
    } else {
        None
    };
    let mut expansions = 0;
    while let Some((key, popped)) = frontier.pop() {
        if let Some(cap) = limit {
            let (int, float) = keys.estimate(key, floats, scale);
            let over = if floats {
                float > (cap / scale as f64) as f32
            } else {
                int as f64 > cap
            };
            if over {
                return Ok(None);
            }
        }
        let state = popped as usize;
        let ci = state / 5;
        let d = state % 5;
        let cell = ((ci % width) as i64, (ci / width) as i64);
        let (g, gf) = scratch.best(state);
        if scratch.flag(ci, TARGET) && d != 0 {
            let crossing = scratch.meta(state).is_some_and(|e| e.crossing.is_some());
            if prepared.query.end_on_crossing || !crossing {
                return Ok(Some(reconstruct(state, scratch, g, prepared, tables)));
            }
            continue;
        }
        expansions += 1;
        if expansions > prepared.query.max_steps {
            return Ok(None);
        }
        let direction = if d == 0 { None } else { Some(DIRS[d - 1]) };
        let straight_only =
            direction.is_some() && scratch.meta(state).is_some_and(|e| e.crossing.is_some());
        for (m, mv) in DIRS.iter().enumerate() {
            let mv_index = m + 1;
            if straight_only && mv_index != d {
                continue;
            }
            if direction.is_some_and(|dd| *mv == (-dd.0, -dd.1)) {
                continue;
            }
            let nxt = (cell.0 + mv.0, cell.1 + mv.1);
            let Some(ni) = prepared.at(nxt) else {
                continue;
            };
            if scratch.flag(ni, SOURCE) || scratch.flag(ni, AVOID) {
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
            let (step_cost, step) = if search.plain(ni) {
                (prepared.query.step, None)
            } else {
                match search.entry(nxt, ni, Some(*mv), false) {
                    Some(e) => (e.cost, Some(e)),
                    None => continue,
                }
            };
            let turn = match direction {
                Some(dd) if dd != *mv => prepared.query.turn,
                _ => 0,
            };
            let extra = start.as_ref().map_or(0, |e| e.cost - prepared.query.step);
            let cost = g + step_cost + turn + extra;
            let mut costf = 0.0f32;
            if floats {
                let mut mv_cost = as_f(step_cost);
                if turn != 0 {
                    mv_cost += as_f(turn);
                }
                costf = gf + mv_cost;
            }
            let nstate = ni * 5 + mv_index;
            let (nbest, nbestf) = scratch.best(nstate);
            let better = if floats { costf < nbestf } else { cost < nbest };
            if better {
                let meta = match step {
                    Some(e)
                        if e.crossing.is_some()
                            || !e.rips.is_empty()
                            || !e.displaces.is_empty() =>
                    {
                        scratch.metas.push(e);
                        (scratch.metas.len() - 1) as u32
                    }
                    _ => EMPTY,
                };
                let begun = match start {
                    Some(e)
                        if e.crossing.is_some()
                            || !e.rips.is_empty()
                            || !e.displaces.is_empty() =>
                    {
                        scratch.starts.push(e);
                        (scratch.starts.len() - 1) as u32
                    }
                    _ => EMPTY,
                };
                scratch.reach(nstate, (cost, costf), state as u32, meta, begun);
                let h = heuristic(nxt);
                let key =
                    keys.key(cost + h, if floats { Some(costf + as_f(h)) } else { None }, scale);
                if !frontier.push(key, counter, nstate as u32) {
                    return Err(());
                }
                counter += 1;
            }
        }
    }
    Ok(None)
}

/// The path back from a target with the crossings, rips and displacements on it.
fn reconstruct(
    state: usize,
    scratch: &Scratch,
    cost: i64,
    prepared: &View,
    tables: &Tables,
) -> Found {
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
        if let Some(step) = scratch.meta(current as usize) {
            if let Some(c) = step.crossing {
                crossings.push((xy, tables.nets[c as usize].clone(), step.reuse));
            }
            for r in &step.rips {
                rips.insert(tables.nets[*r as usize].clone());
            }
            for u in &step.displaces {
                displaces.insert(tables.units[*u as usize].id.clone());
            }
        }
        let previous = scratch.parent(current as usize);
        if let (Some(start), true) = (scratch.start(current as usize), previous != u32::MAX) {
            if let Some(c) = start.crossing {
                crossings.push((cell_of(previous), tables.nets[c as usize].clone(), start.reuse));
            }
            for r in &start.rips {
                rips.insert(tables.nets[*r as usize].clone());
            }
            for u in &start.displaces {
                displaces.insert(tables.units[*u as usize].id.clone());
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
