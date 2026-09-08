//! A* on one layer over the grid, with the pack's crossing, sharing and reservation rules handed in as tables.
//! A port of `state/router/pathfinder.py`: the same costs, the same order of expansion, the same answer.

use std::cmp::Reverse;
use std::collections::{BTreeMap, BTreeSet, BinaryHeap};

use serde::{Deserialize, Serialize};

use super::grid::{Grid, XY};

const DIRS: [XY; 4] = [(1, 0), (0, 1), (-1, 0), (0, -1)];

#[derive(Deserialize)]
pub struct Rules {
    pub net: String,
    pub carrier: String,
    pub step: i64,
    pub turn: i64,
    pub crossing: i64,
    pub share: i64,
    pub corridor: i64,
    pub ripup: i64,
    pub max_steps: i64,
    pub allow_rip: bool,
    #[serde(default)]
    pub protected: BTreeSet<String>,
    #[serde(default)]
    pub walls: Vec<XY>,
    #[serde(default)]
    pub shut: Vec<XY>,
    #[serde(default)]
    pub history: Vec<(i64, i64, i64)>,
    #[serde(default)]
    pub nets: BTreeMap<String, String>,
    #[serde(default)]
    pub share_with: BTreeMap<String, bool>,
    #[serde(default)]
    pub crossings: BTreeMap<String, (String, String)>,
    #[serde(default)]
    pub shapes: BTreeMap<String, Shape>,
    #[serde(default)]
    pub units: BTreeMap<String, String>,
    #[serde(default)]
    pub reservations: BTreeMap<String, Option<i64>>,
}

#[derive(Deserialize, Clone)]
pub struct Shape {
    pub width: i64,
    pub height: i64,
    pub layers: Vec<String>,
}

#[derive(Serialize)]
pub struct Found {
    pub cells: Vec<XY>,
    pub cost: i64,
    pub crossings: Vec<(XY, String, bool)>,
    pub rips: Vec<String>,
}

#[derive(Clone, Default)]
struct Entry {
    cost: i64,
    crossing: Option<String>,
    reuse: bool,
    rip: Option<String>,
}

fn split(holder: &str) -> (&str, &str) {
    match holder.find(':') {
        Some(i) => (&holder[..i], &holder[i + 1..]),
        None => (holder, ""),
    }
}

fn holds_wire(grid: &Grid, layer: &str, xy: XY, net: &str) -> bool {
    grid.holders_at(layer, xy)
        .iter()
        .any(|h| h == &format!("wire:{net}"))
}

fn straight_through(grid: &Grid, layer: &str, other: &str, xy: XY, dir: XY) -> bool {
    let (px, py) = (dir.1, dir.0);
    let (x, y) = xy;
    let across = holds_wire(grid, layer, (x + px, y + py), other)
        && holds_wire(grid, layer, (x - px, y - py), other);
    let along = holds_wire(grid, layer, (x + dir.0, y + dir.1), other)
        || holds_wire(grid, layer, (x - dir.0, y - dir.1), other);
    across && !along
}

struct Search<'a> {
    grid: &'a Grid,
    layer: &'a str,
    rules: &'a Rules,
    walls: BTreeSet<XY>,
    shut: BTreeSet<XY>,
    history: BTreeMap<XY, i64>,
}

impl<'a> Search<'a> {
    fn free_shape(&self, footprint: &str, xy: XY) -> bool {
        let Some(shape) = self.rules.shapes.get(footprint) else {
            return false;
        };
        let cells: Vec<XY> = (0..shape.height)
            .flat_map(|j| (0..shape.width).map(move |i| (xy.0 + i, xy.1 + j)))
            .collect();
        if cells
            .iter()
            .any(|c| c.0 < 0 || c.1 < 0 || c.0 >= self.grid.width || c.1 >= self.grid.height)
        {
            return false;
        }
        shape
            .layers
            .iter()
            .all(|layer| self.grid.free_for(layer, &cells))
    }

    fn entry(&self, xy: XY, dir: Option<XY>) -> Option<Entry> {
        let (x, y) = xy;
        if x < 0
            || y < 0
            || x >= self.grid.width
            || y >= self.grid.height
            || self.walls.contains(&xy)
            || self.shut.contains(&xy)
        {
            return None;
        }
        let holders = self.grid.holders_at(self.layer, xy);
        let mut result = Entry { cost: self.rules.step, ..Entry::default() };
        if holders.is_empty() {
            return Some(result);
        }
        let mut unit_ref: Option<&str> = None;
        for holder in &holders {
            let (kind, reference) = split(holder);
            match kind {
                "cell" => return None,
                "reserve" => match self.rules.reservations.get(reference) {
                    Some(Some(price)) => result.cost += price,
                    _ => return None,
                },
                "unit" => unit_ref = Some(reference),
                "wire" => {
                    if reference == self.rules.net {
                        return None;
                    }
                    let other_carrier = self.rules.nets.get(reference).cloned().unwrap_or_default();
                    if *self.rules.share_with.get(&other_carrier).unwrap_or(&false) {
                        result.cost += self.rules.share;
                        continue;
                    }
                    let mode = self
                        .rules
                        .crossings
                        .get(&other_carrier)
                        .map(|c| c.0.as_str())
                        .unwrap_or("forbidden");
                    if mode != "forbidden" {
                        if let Some(d) = dir {
                            if straight_through(self.grid, self.layer, reference, xy, d) {
                                result.crossing = Some(reference.to_string());
                                result.cost += self.rules.crossing;
                                continue;
                            }
                        }
                    }
                    if self.rules.allow_rip && !self.rules.protected.contains(reference) {
                        result.rip = Some(reference.to_string());
                        result.cost +=
                            self.rules.ripup * (1 + self.history.get(&xy).cloned().unwrap_or(0));
                        continue;
                    }
                    return None;
                }
                _ => {}
            }
        }
        if let Some(unit) = unit_ref {
            let Some(crossing) = &result.crossing else {
                return None;
            };
            let other_carrier = self.rules.nets.get(crossing).cloned().unwrap_or_default();
            let (mode, footprint) = self
                .rules
                .crossings
                .get(&other_carrier)
                .cloned()
                .unwrap_or(("forbidden".to_string(), String::new()));
            let unit_footprint = self.rules.units.get(unit).cloned().unwrap_or_default();
            if mode != "unit" || footprint.is_empty() || unit_footprint != footprint {
                return None;
            }
            result.reuse = true;
        } else if let Some(crossing) = &result.crossing {
            let other_carrier = self.rules.nets.get(crossing).cloned().unwrap_or_default();
            let (mode, footprint) = self
                .rules
                .crossings
                .get(&other_carrier)
                .cloned()
                .unwrap_or(("forbidden".to_string(), String::new()));
            let only_wires = holders.iter().all(|h| split(h).0 == "wire");
            if mode == "unit"
                && (footprint.is_empty() || !only_wires || !self.free_shape(&footprint, xy))
            {
                return None;
            }
        }
        Some(result)
    }
}

type State = (XY, Option<XY>);
type Queued = Reverse<(i64, i64, XY, Option<XY>)>;

pub fn find(
    grid: &Grid,
    layer: &str,
    sources: &[XY],
    targets: &[XY],
    avoid: &[XY],
    rules: &Rules,
) -> Option<Found> {
    if sources.is_empty() || targets.is_empty() {
        return None;
    }
    let search = Search {
        grid,
        layer,
        rules,
        walls: rules.walls.iter().cloned().collect(),
        shut: rules.shut.iter().cloned().collect(),
        history: rules
            .history
            .iter()
            .map(|(x, y, n)| ((*x, *y), *n))
            .collect(),
    };
    let target_set: BTreeSet<XY> = targets.iter().cloned().collect();
    let source_set: BTreeSet<XY> = sources.iter().cloned().collect();
    let avoid_set: BTreeSet<XY> = avoid.iter().cloned().collect();
    let goals: Vec<XY> = target_set.iter().cloned().collect();
    let heuristic = |cell: XY| -> i64 {
        if goals.len() > 32 {
            0
        } else {
            goals
                .iter()
                .map(|g| (cell.0 - g.0).abs() + (cell.1 - g.1).abs())
                .min()
                .unwrap_or(0)
        }
    };
    let mut best: BTreeMap<State, i64> = BTreeMap::new();
    let mut parent: BTreeMap<State, Option<State>> = BTreeMap::new();
    let mut meta: BTreeMap<State, Entry> = BTreeMap::new();
    let mut heap: BinaryHeap<Queued> = BinaryHeap::new();
    let mut counter: i64 = 0;
    for cell in source_set.iter() {
        let state = (*cell, None);
        best.insert(state, 0);
        parent.insert(state, None);
        heap.push(Reverse((heuristic(*cell), counter, *cell, None)));
        counter += 1;
    }
    let mut expansions = 0;
    while let Some(Reverse((_, _, cell, direction))) = heap.pop() {
        let state = (cell, direction);
        let g = best[&state];
        if target_set.contains(&cell) && direction.is_some() {
            return Some(reconstruct(state, &parent, &meta, g));
        }
        expansions += 1;
        if expansions > rules.max_steps {
            return None;
        }
        let moves: Vec<XY> = match (meta.get(&state), direction) {
            (Some(here), Some(d)) if here.crossing.is_some() => vec![d],
            _ => DIRS.to_vec(),
        };
        for mv in moves {
            let nxt = (cell.0 + mv.0, cell.1 + mv.1);
            if source_set.contains(&nxt) || avoid_set.contains(&nxt) {
                continue;
            }
            let Some(step) = search.entry(nxt, Some(mv)) else {
                continue;
            };
            if step.crossing.is_some() && target_set.contains(&nxt) {
                continue;
            }
            let turn = match direction {
                Some(d) if d != mv => rules.turn,
                _ => 0,
            };
            let cost = g + step.cost + turn;
            let nstate = (nxt, Some(mv));
            if cost < *best.get(&nstate).unwrap_or(&(cost + 1)) {
                best.insert(nstate, cost);
                parent.insert(nstate, Some(state));
                meta.insert(nstate, step);
                heap.push(Reverse((cost + heuristic(nxt), counter, nxt, Some(mv))));
                counter += 1;
            }
        }
    }
    None
}

fn reconstruct(
    state: State,
    parent: &BTreeMap<State, Option<State>>,
    meta: &BTreeMap<State, Entry>,
    cost: i64,
) -> Found {
    let mut cells = Vec::new();
    let mut crossings = Vec::new();
    let mut rips = BTreeSet::new();
    let mut current = Some(state);
    while let Some(s) = current {
        cells.push(s.0);
        if let Some(step) = meta.get(&s) {
            if let Some(c) = &step.crossing {
                crossings.push((s.0, c.clone(), step.reuse));
            }
            if let Some(r) = &step.rip {
                rips.insert(r.clone());
            }
        }
        current = parent.get(&s).cloned().flatten();
    }
    cells.reverse();
    crossings.reverse();
    Found { cells, cost, crossings, rips: rips.into_iter().collect() }
}
