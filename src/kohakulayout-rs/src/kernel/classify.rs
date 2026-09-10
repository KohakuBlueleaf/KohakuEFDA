//! The tables one A* search reads: the rules as handed in, their names as indices, and a layer's cells
//! classified once per grid state, each priced for entry with its crossing, rip and displacement.

use std::collections::{BTreeMap, BTreeSet, HashMap};

use serde::Deserialize;

use super::grid::{Grid, XY};

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
    pub shut: Vec<XY>,
    #[serde(default)]
    pub held: Vec<XY>,
    #[serde(default)]
    pub ports: Vec<(i64, i64, i64, i64)>,
    #[serde(default)]
    pub history: Vec<(i64, i64, i64)>,
    #[serde(default)]
    pub nets: BTreeMap<String, String>,
    #[serde(default)]
    pub share_with: BTreeMap<String, bool>,
    #[serde(default)]
    pub crossings: BTreeMap<String, (String, String, bool)>,
    #[serde(default)]
    pub shapes: BTreeMap<String, Shape>,
    #[serde(default)]
    pub units: BTreeMap<String, String>,
    #[serde(default)]
    pub unit_owners: BTreeMap<String, String>,
    #[serde(default)]
    pub unit_fields: BTreeMap<String, bool>,
    #[serde(default)]
    pub all_nets: BTreeSet<String>,
    #[serde(default)]
    pub reservations: BTreeMap<String, Option<i64>>,
}

fn yes() -> bool {
    true
}

#[derive(Deserialize, Clone)]
pub struct Shape {
    pub width: i64,
    pub height: i64,
    pub layers: Vec<String>,
}

/// The rules with their cell tables laid out as grids, prepared once and shared by every search over them.
pub struct Prepared {
    pub rules: Rules,
    pub(super) width: usize,
    pub(super) height: usize,
    pub(super) walls: Vec<bool>,
    pub(super) shut: Vec<bool>,
    pub(super) held: Vec<bool>,
    pub(super) history: Vec<i64>,
    pub(super) ports: HashMap<usize, XY>,
    pub(super) names: Names,
}

impl Prepared {
    pub fn new(rules: Rules, width: i64, height: i64, walls: &[XY]) -> Prepared {
        let (w, h) = (width.max(0) as usize, height.max(0) as usize);
        let cells = w * h;
        let names = Names::new(&rules);
        let mut out = Prepared {
            names,
            rules,
            width: w,
            height: h,
            walls: vec![false; cells],
            shut: vec![false; cells],
            held: vec![false; cells],
            history: vec![0; cells],
            ports: HashMap::new(),
        };
        for (ax, ay, px, py) in out.rules.ports.clone() {
            if let Some(i) = out.at((ax, ay)) {
                out.ports.insert(i, (px, py));
            }
        }
        for xy in out.rules.walls.clone().iter().chain(walls.iter()) {
            if let Some(i) = out.at(*xy) {
                out.walls[i] = true;
            }
        }
        for xy in out.rules.shut.clone() {
            if let Some(i) = out.at(xy) {
                out.shut[i] = true;
            }
        }
        for xy in out.rules.held.clone() {
            if let Some(i) = out.at(xy) {
                out.held[i] = true;
            }
        }
        for (x, y, n) in out.rules.history.clone() {
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

/// The rules' names as indices, so a probe compares numbers: nets with their sharing, crossing and protection, units with their footprint and owner.
pub(super) struct Names {
    pub(super) nets: Vec<String>,
    pub(super) net_index: HashMap<String, u32>,
    share: Vec<bool>,
    cross_mode: Vec<u8>,
    cross_unit: Vec<String>,
    cross_bent: Vec<bool>,
    protected: Vec<bool>,
    known: Vec<bool>,
    pub(super) unit_index: HashMap<String, u32>,
    pub(super) unit_ids: Vec<String>,
    pub(super) unit_footprint: Vec<String>,
    pub(super) unit_owner: Vec<Option<u32>>,
    pub(super) unit_field: Vec<bool>,
}

impl Names {
    fn new(rules: &Rules) -> Names {
        let mut names = Names {
            nets: Vec::new(),
            net_index: HashMap::new(),
            share: Vec::new(),
            cross_mode: Vec::new(),
            cross_unit: Vec::new(),
            cross_bent: Vec::new(),
            protected: Vec::new(),
            known: Vec::new(),
            unit_index: HashMap::new(),
            unit_ids: Vec::new(),
            unit_footprint: Vec::new(),
            unit_owner: Vec::new(),
            unit_field: Vec::new(),
        };
        let mut all: BTreeSet<&str> = rules.nets.keys().map(String::as_str).collect();
        all.extend(rules.all_nets.iter().map(String::as_str));
        all.extend(rules.unit_owners.values().map(String::as_str));
        all.extend(rules.protected.iter().map(String::as_str));
        for net in all {
            let carrier = rules.nets.get(net).map(String::as_str).unwrap_or("");
            let (mode, unit, bent) = rules
                .crossings
                .get(carrier)
                .map(|c| (c.0.as_str(), c.1.clone(), c.2))
                .unwrap_or(("forbidden", String::new(), false));
            names
                .net_index
                .insert(net.to_string(), names.nets.len() as u32);
            names.nets.push(net.to_string());
            names
                .share
                .push(*rules.share_with.get(carrier).unwrap_or(&false));
            names.cross_mode.push(match mode {
                "forbidden" => 0,
                "unit" => 2,
                _ => 1,
            });
            names.cross_unit.push(unit);
            names.cross_bent.push(bent);
            names.protected.push(rules.protected.contains(net));
            names.known.push(rules.all_nets.contains(net));
        }
        for (unit, footprint) in &rules.units {
            names
                .unit_index
                .insert(unit.clone(), names.unit_footprint.len() as u32);
            names.unit_ids.push(unit.clone());
            names.unit_footprint.push(footprint.clone());
            let owner = rules
                .unit_owners
                .get(unit)
                .and_then(|o| names.net_index.get(o).copied());
            names.unit_owner.push(owner);
            names
                .unit_field
                .push(*rules.unit_fields.get(unit).unwrap_or(&false));
        }
        names
    }
}

#[derive(Clone, Copy)]
pub(super) struct WireRef {
    net: u32,
    share: bool,
    cross: bool,
    rippable: bool,
}

/// One cell of the layer as the search sees it: closed outright, priced, under a unit, or held by wires.
#[derive(Clone, Default)]
pub(super) struct Cell {
    blocked: bool,
    extra: i64,
    unit: Option<u32>,
    unknown_unit: bool,
    wires: Vec<WireRef>,
    only_wires: bool,
}

#[derive(Clone, Default)]
pub(super) struct Entry {
    pub(super) cost: i64,
    pub(super) crossing: Option<u32>,
    pub(super) reuse: bool,
    pub(super) rips: Vec<u32>,
    pub(super) displaces: Vec<u32>,
}

fn split(holder: &str) -> (&str, &str) {
    match holder.find(':') {
        Some(i) => (&holder[..i], &holder[i + 1..]),
        None => (holder, ""),
    }
}

/// One search's view of a layer: the grid, its classified cells and the prepared rules.
pub(super) struct Search<'a> {
    pub(super) grid: &'a Grid,
    pub(super) cells: &'a [Cell],
    pub(super) prepared: &'a Prepared,
    pub(super) own: &'a [u8],
    pub(super) me: Option<u32>,
}

impl<'a> Search<'a> {
    pub(super) fn classify(grid: &Grid, layer: &str, prepared: &Prepared) -> Vec<Cell> {
        let rules = &prepared.rules;
        let names = &prepared.names;
        let mut cells = vec![Cell::default(); prepared.width * prepared.height];
        let Some(map) = grid.layer_map(layer) else {
            return cells;
        };
        for (xy, held) in map {
            let Some(i) = prepared.at(*xy) else {
                continue;
            };
            let cell = &mut cells[i];
            cell.only_wires = !held.is_empty();
            for holder in held {
                let (kind, reference) = split(holder);
                match kind {
                    "cell" => {
                        cell.blocked = true;
                        cell.only_wires = false;
                    }
                    "reserve" => {
                        cell.only_wires = false;
                        match rules.reservations.get(reference) {
                            Some(Some(price)) => cell.extra += price,
                            _ => cell.blocked = true,
                        }
                    }
                    "unit" => match names.unit_index.get(reference) {
                        Some(u) => {
                            cell.unit = Some(*u);
                            if !names.unit_field[*u as usize] {
                                cell.only_wires = false;
                            }
                        }
                        None => {
                            cell.unknown_unit = true;
                            cell.only_wires = false;
                        }
                    },
                    "wire" => {
                        if reference == rules.net {
                            cell.blocked = true;
                            continue;
                        }
                        let Some(net) = names.net_index.get(reference).copied() else {
                            cell.blocked = true;
                            continue;
                        };
                        let n = net as usize;
                        cell.wires.push(WireRef {
                            net,
                            share: names.share[n],
                            cross: names.cross_mode[n] != 0,
                            rippable: !names.protected[n],
                        });
                    }
                    _ => {}
                }
            }
        }
        cells
    }

    pub(super) fn holds_wire(&self, xy: XY, net: u32) -> bool {
        match self.prepared.at(xy) {
            Some(i) => self.cells[i].wires.iter().any(|w| w.net == net),
            None => false,
        }
    }

    pub(super) fn straight_through(&self, other: u32, xy: XY, dir: XY, terminal: bool) -> bool {
        let (px, py) = (dir.1, dir.0);
        let (x, y) = xy;
        let port = self
            .prepared
            .at(xy)
            .and_then(|i| self.prepared.ports.get(&i).cloned());
        let side = |n: XY| self.holds_wire(n, other) || port == Some(n);
        if terminal && self.prepared.names.cross_bent[other as usize] {
            return side((x + px, y + py)) || side((x - px, y - py));
        }
        let across = side((x + px, y + py)) && side((x - px, y - py));
        let along = self.holds_wire((x + dir.0, y + dir.1), other)
            || self.holds_wire((x - dir.0, y - dir.1), other);
        across && !along
    }

    /// Whether a unit's shape has its occluded layers free at `xy`, a displaced unit's holder not counted.
    pub(super) fn free_shape(&self, footprint: &str, xy: XY, ignore: Option<&str>) -> bool {
        let Some(shape) = self.prepared.rules.shapes.get(footprint) else {
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

    /// The cost of crossing one of the net's own standing lanes: across its run only, with the carrier's own crossing unit where one is needed.
    fn own_crossing(&self, xy: XY, index: usize, dir: Option<XY>) -> Option<Entry> {
        let d = dir?;
        let along = if self.own[index] == 1 {
            d.1 == 0
        } else {
            d.0 == 0
        };
        if along {
            return None;
        }
        let me = self.me?;
        let names = &self.prepared.names;
        let m = me as usize;
        if names.cross_mode[m] == 0 {
            return None;
        }
        let cell = &self.cells[index];
        if !cell.wires.is_empty() || cell.unit.is_some() || cell.unknown_unit {
            return None;
        }
        if names.cross_mode[m] == 2 {
            let footprint = &names.cross_unit[m];
            if footprint.is_empty() || !self.free_shape(footprint, xy, None) {
                return None;
            }
        }
        Some(Entry {
            cost: self.prepared.rules.step + self.prepared.rules.crossing,
            crossing: Some(me),
            ..Entry::default()
        })
    }

    /// The cost of entering a cell moving `dir`, or None when it is closed; a `terminal` is the path's own start, where only what holds the cell matters; a cell of the net's own standing lanes is crossed, at either end or on the way.
    pub(super) fn entry(
        &self,
        xy: XY,
        index: usize,
        dir: Option<XY>,
        terminal: bool,
    ) -> Option<Entry> {
        let rules = &self.prepared.rules;
        let names = &self.prepared.names;
        if !terminal && (self.prepared.walls[index] || self.prepared.shut[index]) {
            return None;
        }
        let cell = &self.cells[index];
        if cell.blocked {
            return None;
        }
        if self.own[index] != 0 {
            return self.own_crossing(xy, index, dir);
        }
        let mut result = Entry { cost: rules.step + cell.extra, ..Entry::default() };
        if cell.wires.is_empty() && cell.unit.is_none() && !cell.unknown_unit {
            return Some(result);
        }
        let held = self.prepared.held[index];
        let rip_cost = rules.ripup * (1 + self.prepared.history[index]);
        for wire in &cell.wires {
            if wire.share {
                result.cost += rules.share;
                continue;
            }
            if wire.cross {
                if let Some(d) = dir {
                    if self.straight_through(wire.net, xy, d, terminal) {
                        result.crossing = Some(wire.net);
                        result.cost += rules.crossing;
                        continue;
                    }
                }
            }
            if rules.allow_rip && wire.rippable && !held {
                result.rips.push(wire.net);
                result.cost += rip_cost;
                continue;
            }
            return None;
        }
        let mut unit = cell.unit;
        if let Some(u) = unit.filter(|u| names.unit_field[*u as usize]) {
            result.displaces.push(u);
            result.cost += rules.displace;
            unit = None;
        }
        if unit.is_some() || cell.unknown_unit {
            let owner = unit.and_then(|u| names.unit_owner[u as usize]);
            if let Some(crossing) = result.crossing {
                let c = crossing as usize;
                let footprint = &names.cross_unit[c];
                let unit_footprint = unit
                    .map(|u| names.unit_footprint[u as usize].as_str())
                    .unwrap_or("");
                if names.cross_mode[c] != 2 || footprint.is_empty() || unit_footprint != footprint {
                    return None;
                }
                result.reuse = true;
            } else if owner.is_some_and(|o| result.rips.contains(&o)) {
            } else {
                let rippable = owner.filter(|o| {
                    let n = *o as usize;
                    names.known[n] && rules.allow_rip && !names.protected[n] && !held
                });
                let o = rippable?;
                result.rips.push(o);
                result.cost += rip_cost;
            }
        } else if let Some(crossing) = result.crossing {
            let c = crossing as usize;
            let footprint = &names.cross_unit[c];
            let gone = result
                .displaces
                .first()
                .map(|u| format!("unit:{}", names.unit_ids[*u as usize]));
            if names.cross_mode[c] == 2
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
