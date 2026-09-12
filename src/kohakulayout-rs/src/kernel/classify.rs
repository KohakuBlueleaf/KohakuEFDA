//! The tables one A* search reads: a layer's cells classified once per grid state, for every net at
//! once, and one search's query laid out as grids, so each cell is priced for entry with its
//! crossing, rip and displacement when the search reaches it.

use std::collections::BTreeSet;
use std::sync::Arc;

use serde::Deserialize;

use super::grid::{Grid, XY};
use super::tables::{CarrierView, Tables};

/// One search's rules: its net, carrier and costs, and the cells shut, held or charged for it.
#[derive(Deserialize)]
pub struct Query {
    pub net: String,
    pub carrier: String,
    pub step: i64,
    pub turn: i64,
    pub crossing: i64,
    pub share: i64,
    pub corridor: i64,
    pub ripup: i64,
    #[serde(default)]
    pub displace: i64,
    pub max_steps: i64,
    #[serde(default)]
    pub detour: f64,
    #[serde(default)]
    pub slack: f64,
    pub allow_rip: bool,
    #[serde(default = "yes")]
    pub end_on_crossing: bool,
    #[serde(default)]
    pub float_scale: i64,
    #[serde(default)]
    pub protected: BTreeSet<String>,
    #[serde(default)]
    pub walls: Vec<XY>,
    #[serde(default)]
    pub walls_key: String,
    #[serde(default)]
    pub unit_walls_key: String,
    #[serde(default)]
    pub shut: Vec<XY>,
    #[serde(default)]
    pub held: Vec<XY>,
    #[serde(default)]
    pub history: Vec<(i64, i64, i64)>,
}

fn yes() -> bool {
    true
}

/// A query with its cell sets laid out as grids and its net names as indices.
pub struct View {
    pub query: Query,
    pub(super) width: usize,
    pub(super) height: usize,
    pub(super) walls: Arc<Vec<bool>>,
    pub(super) unit_walls: Arc<Vec<bool>>,
    pub(super) shut: Vec<bool>,
    pub(super) held: Vec<bool>,
    pub(super) history: Vec<i64>,
    pub(super) protected: Vec<bool>,
    pub(super) me: Option<u32>,
}

impl View {
    /// Lay a query out over the shared `walls` and `unit_walls` grids.
    pub fn new(
        query: Query,
        width: i64,
        height: i64,
        walls: Arc<Vec<bool>>,
        unit_walls: Arc<Vec<bool>>,
        tables: &Tables,
    ) -> View {
        let (w, h) = (width.max(0) as usize, height.max(0) as usize);
        let cells = w * h;
        let mut out = View {
            me: tables.net(&query.net),
            protected: tables
                .nets
                .iter()
                .map(|n| query.protected.contains(n))
                .collect(),
            query,
            width: w,
            height: h,
            walls,
            unit_walls,
            shut: vec![false; cells],
            held: vec![false; cells],
            history: vec![0; cells],
        };
        if !out.query.walls.is_empty() {
            let mut merged = (*out.walls).clone();
            for xy in out.query.walls.clone() {
                if let Some(i) = out.at(xy) {
                    merged[i] = true;
                }
            }
            out.walls = Arc::new(merged);
        }
        for xy in out.query.shut.clone() {
            if let Some(i) = out.at(xy) {
                out.shut[i] = true;
            }
        }
        for xy in out.query.held.clone() {
            if let Some(i) = out.at(xy) {
                out.held[i] = true;
            }
        }
        for (x, y, n) in out.query.history.clone() {
            if let Some(i) = out.at((x, y)) {
                out.history[i] = n;
            }
        }
        out
    }

    pub(super) fn at(&self, xy: XY) -> Option<usize> {
        if xy.0 < 0 || xy.1 < 0 || xy.0 >= self.width as i64 || xy.1 >= self.height as i64 {
            None
        } else {
            Some(xy.1 as usize * self.width + xy.0 as usize)
        }
    }
}

/// One classified cell: blocked, reserved, under a unit, or held by wires with their runs.
#[derive(Clone, Default)]
pub struct Cell {
    blocked: bool,
    reserves: Vec<u32>,
    unit: Option<u32>,
    unknown_unit: bool,
    wires: Vec<(u32, u8)>,
    only_wires: bool,
}

impl Cell {
    /// Whether nothing holds the cell.
    pub fn is_empty(&self) -> bool {
        !self.blocked
            && self.reserves.is_empty()
            && self.unit.is_none()
            && !self.unknown_unit
            && self.wires.is_empty()
    }
}

#[derive(Clone, Default)]
pub(super) struct Entry {
    pub(super) cost: i64,
    pub(super) crossing: Option<u32>,
    pub(super) reuse: bool,
    pub(super) rips: Vec<u32>,
    pub(super) displaces: Vec<u32>,
}

/// The run bit of a unit step: `N=1 E=2 S=4 W=8`.
fn side_bit(dx: i64, dy: i64) -> u8 {
    match (dx, dy) {
        (0, -1) => 1,
        (1, 0) => 2,
        (0, 1) => 4,
        (-1, 0) => 8,
        _ => 0,
    }
}

fn split(holder: &str) -> (&str, &str) {
    match holder.find(':') {
        Some(i) => (&holder[..i], &holder[i + 1..]),
        None => (holder, ""),
    }
}

/// Classify one cell's holders; a wire of an unknown net blocks the cell.
pub fn classify_cell(grid: &Grid, layer: &str, tables: &Tables, xy: XY, held: &[String]) -> Cell {
    let mut cell = Cell { only_wires: !held.is_empty(), ..Cell::default() };
    for holder in held {
        let (kind, reference) = split(holder);
        match kind {
            "cell" => {
                cell.blocked = true;
                cell.only_wires = false;
            }
            "reserve" => {
                cell.only_wires = false;
                match tables.reservation_index.get(reference) {
                    Some(index) => cell.reserves.push(*index),
                    None => cell.blocked = true,
                }
            }
            "unit" => match tables.unit_index.get(reference) {
                Some(u) => {
                    cell.unit = Some(*u);
                    if !tables.units[*u as usize].field {
                        cell.only_wires = false;
                    }
                }
                None => {
                    cell.unknown_unit = true;
                    cell.only_wires = false;
                }
            },
            "wire" => match tables.net(reference) {
                Some(net) => cell.wires.push((net, grid.run_at(layer, holder, xy))),
                None => cell.blocked = true,
            },
            _ => {}
        }
    }
    cell
}

/// A layer's cells for the tables, for every net at once.
pub fn classify(grid: &Grid, layer: &str, tables: &Tables) -> Vec<Cell> {
    let (w, h) = (grid.width.max(0) as usize, grid.height.max(0) as usize);
    let mut cells = vec![Cell::default(); w * h];
    let Some(map) = grid.layer_map(layer) else {
        return cells;
    };
    for (xy, held) in map {
        if xy.0 < 0 || xy.1 < 0 || xy.0 >= w as i64 || xy.1 >= h as i64 {
            continue;
        }
        cells[xy.1 as usize * w + xy.0 as usize] = classify_cell(grid, layer, tables, *xy, held);
    }
    cells
}

/// One search over a classified layer.
pub(super) struct Search<'a> {
    pub(super) grid: &'a Grid,
    pub(super) cells: &'a [Cell],
    pub(super) empty: &'a [bool],
    pub(super) view: &'a View,
    pub(super) carrier: &'a CarrierView,
    pub(super) tables: &'a Tables,
    pub(super) own: &'a [u8],
}

impl<'a> Search<'a> {
    /// Whether a move along `dir` crosses a wire with run `run` straight.
    pub(super) fn straight_through(&self, other: u32, run: u8, dir: XY, terminal: bool) -> bool {
        let (px, py) = (dir.1, dir.0);
        let side = |dx: i64, dy: i64| run & side_bit(dx, dy) != 0;
        if terminal && self.carrier.cross_bent[other as usize] {
            return side(px, py) || side(-px, -py);
        }
        let across = side(px, py) && side(-px, -py);
        let along = side(dir.0, dir.1) || side(-dir.0, -dir.1);
        across && !along
    }

    /// Whether a unit's occluded layers are free at `xy`, the holder `ignore` not counted.
    pub(super) fn free_shape(&self, footprint: &str, xy: XY, ignore: Option<&str>) -> bool {
        let Some(shape) = self.tables.shapes.get(footprint) else {
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
        match ignore {
            None => shape
                .layers
                .iter()
                .all(|layer| self.grid.free_for(layer, &cells)),
            Some(holder) => shape.layers.iter().all(|layer| {
                cells
                    .iter()
                    .all(|c| self.grid.holders_at(layer, *c).iter().all(|h| h == holder))
            }),
        }
    }

    /// The cost of crossing one of the net's own lanes, across its run only.
    fn own_crossing(&self, xy: XY, index: usize, dir: Option<XY>) -> Option<Entry> {
        let dir = dir?;
        let along = if self.own[index] == 1 {
            dir.1 == 0
        } else {
            dir.0 == 0
        };
        if along {
            return None;
        }
        let me = self.view.me?;
        if self.carrier.own_mode == 0 {
            return None;
        }
        let cell = &self.cells[index];
        if !cell.wires.is_empty() || cell.unit.is_some() || cell.unknown_unit {
            return None;
        }
        if self.carrier.own_mode == 2 {
            let footprint = &self.carrier.own_unit;
            if footprint.is_empty()
                || self.view.unit_walls[index]
                || !self.free_shape(footprint, xy, None)
            {
                return None;
            }
        }
        Some(Entry {
            cost: self.view.query.step + self.view.query.crossing,
            crossing: Some(me),
            ..Entry::default()
        })
    }

    /// Whether a cell costs one step and records nothing: open, empty and off the owned axes.
    #[inline]
    pub(super) fn plain(&self, index: usize) -> bool {
        self.empty[index]
            && self.own[index] == 0
            && !self.view.walls[index]
            && !self.view.shut[index]
    }

    /// The cost of entering a cell moving `dir`, or None when it is closed.
    pub(super) fn entry(
        &self,
        xy: XY,
        index: usize,
        dir: Option<XY>,
        terminal: bool,
    ) -> Option<Entry> {
        let view = self.view;
        let query = &view.query;
        let tables = self.tables;
        if !terminal && (view.walls[index] || view.shut[index]) {
            return None;
        }
        if self.empty[index] && self.own[index] == 0 {
            return Some(Entry { cost: query.step, ..Entry::default() });
        }
        let cell = &self.cells[index];
        if cell.blocked || cell.wires.iter().any(|(net, _)| Some(*net) == view.me) {
            return None;
        }
        if self.own[index] != 0 {
            return self.own_crossing(xy, index, dir);
        }
        let mut result = Entry { cost: query.step, ..Entry::default() };
        for reservation in &cell.reserves {
            if tables.reservations[*reservation as usize] != query.carrier {
                return None;
            }
            result.cost += query.corridor;
        }
        if cell.wires.is_empty() && cell.unit.is_none() && !cell.unknown_unit {
            return Some(result);
        }
        let held = view.held[index];
        let rip_cost = query.ripup * (1 + view.history[index]);
        for (net, run) in &cell.wires {
            let n = *net as usize;
            if self.carrier.share[n] {
                result.cost += query.share;
                continue;
            }
            let mode = self.carrier.cross_mode[n];
            if mode != 0 && (mode != 2 || !view.unit_walls[index]) {
                if let Some(d) = dir {
                    if self.straight_through(*net, *run, d, terminal) {
                        result.crossing = Some(*net);
                        result.cost += query.crossing;
                        continue;
                    }
                }
            }
            if query.allow_rip && !view.protected[n] && !held {
                result.rips.push(*net);
                result.cost += rip_cost;
                continue;
            }
            return None;
        }
        let mut unit = cell.unit;
        if let Some(u) = unit.filter(|u| tables.units[*u as usize].field) {
            result.displaces.push(u);
            result.cost += query.displace;
            unit = None;
        }
        if unit.is_some() || cell.unknown_unit {
            let owner = unit.and_then(|u| tables.net(&tables.units[u as usize].owner));
            if let Some(crossing) = result.crossing {
                let c = crossing as usize;
                let footprint = &self.carrier.cross_unit[c];
                let unit_footprint = unit
                    .map(|u| tables.units[u as usize].footprint.as_str())
                    .unwrap_or("");
                if self.carrier.cross_mode[c] != 2
                    || footprint.is_empty()
                    || unit_footprint != footprint
                {
                    return None;
                }
                result.reuse = true;
            } else if owner.is_some_and(|o| result.rips.contains(&o)) {
            } else {
                let o =
                    owner.filter(|o| query.allow_rip && !view.protected[*o as usize] && !held)?;
                result.rips.push(o);
                result.cost += rip_cost;
            }
        } else if let Some(crossing) = result.crossing {
            let c = crossing as usize;
            let footprint = &self.carrier.cross_unit[c];
            let gone = result
                .displaces
                .first()
                .map(|u| format!("unit:{}", tables.units[*u as usize].id));
            if self.carrier.cross_mode[c] == 2
                && (footprint.is_empty()
                    || !cell.only_wires
                    || !self.free_shape(footprint, xy, gone.as_deref()))
            {
                return None;
            }
        }
        Some(result)
    }
}
