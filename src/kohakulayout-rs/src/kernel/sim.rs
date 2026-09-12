//! The simulated world a native call changes and then undoes: the grid and its classified layers
//! under an undo log, the mirror's wires, units and attach tables read through overlays, and the
//! twins of the world's attach, wiring and unit methods over them.

use super::grid::{Grid, XY};
use super::hash::Set;
use super::judge::{holders, kind_of};
use super::lanes::xy_text;
use super::layers::Layers;
use super::overlay::{AttachOver, Overlay};
use super::records::{Placed, Records, Unit, Wire};
use super::spec::Terminal;
use super::tables::Tables;

/// Why the pass hands a case back to Python.
pub type Decline = String;

/// One write the undo log reverts.
enum Undo {
    Occupied(String, Vec<XY>, String),
    Freed(String, Vec<XY>, String),
    Runs(String, String, Vec<(XY, u8)>),
}

/// The cells a footprint covers at an anchor, rows of its rotated size.
pub fn footprint_cells(x: i64, y: i64, width: i64, height: i64, rot: i64) -> Vec<XY> {
    let (w, h) = if rot % 180 == 90 {
        (height, width)
    } else {
        (width, height)
    };
    (0..h)
        .flat_map(|j| (0..w).map(move |i| (x + i, y + j)))
        .collect()
}

pub struct Sim<'a> {
    /// The cell a native attempt places, visible once its footprint is written.
    pub extra: Option<(&'a str, &'a Placed)>,
    /// Whether the attempt's own cell is written yet.
    pub shown: bool,
    pub grid: &'a mut Grid,
    pub layers: &'a mut Layers,
    pub tables: &'a mut Tables,
    pub rec: &'a Records,
    pub wires: Overlay<'a, String, Wire>,
    pub units: Overlay<'a, String, Unit>,
    pub attach: AttachOver<'a>,
    pub unit_seq: u64,
    undo: Vec<Undo>,
}

impl<'a> Sim<'a> {
    pub fn new(
        grid: &'a mut Grid,
        layers: &'a mut Layers,
        tables: &'a mut Tables,
        rec: &'a Records,
    ) -> Sim<'a> {
        layers.checkpoint();
        Sim {
            extra: None,
            shown: false,
            grid,
            layers,
            tables,
            rec,
            wires: Overlay::new(&rec.wires),
            units: Overlay::new(&rec.units),
            attach: AttachOver::new(&rec.attach),
            unit_seq: rec.unit_seq,
            undo: Vec::new(),
        }
    }

    fn touch(&mut self, layer: &str, cells: &[XY]) {
        let (w, h) = (self.grid.width, self.grid.height);
        self.layers.touch(layer, cells, w, h);
    }

    pub fn occupy(&mut self, layer: &str, cells: &[XY], holder: &str) {
        self.grid.occupy(layer, cells, holder);
        self.touch(layer, cells);
        self.undo
            .push(Undo::Occupied(layer.into(), cells.to_vec(), holder.into()));
    }

    pub fn free(&mut self, layer: &str, cells: &[XY], holder: &str) {
        self.grid.free(layer, cells, holder);
        self.touch(layer, cells);
        self.undo
            .push(Undo::Freed(layer.into(), cells.to_vec(), holder.into()));
    }

    /// Write a holder's runs, the undo writing `old` back as the world's journal does.
    pub fn set_runs(&mut self, layer: &str, holder: &str, runs: &[(XY, u8)], old: Vec<(XY, u8)>) {
        self.grid.set_runs(layer, holder, runs);
        let cells: Vec<XY> = runs.iter().map(|r| r.0).collect();
        self.touch(layer, &cells);
        self.undo.push(Undo::Runs(layer.into(), holder.into(), old));
    }

    /// Undo every write, the grid and its classified layers back as they were.
    pub fn finish(mut self) {
        while let Some(op) = self.undo.pop() {
            match op {
                Undo::Occupied(layer, cells, holder) => {
                    self.grid.free(&layer, &cells, &holder);
                }
                Undo::Freed(layer, cells, holder) => {
                    self.grid.occupy(&layer, &cells, &holder);
                }
                Undo::Runs(layer, holder, old) => {
                    self.grid.set_runs(&layer, &holder, &old);
                }
            }
        }
        self.layers.restore();
    }

    pub fn in_grid(&self, xy: XY) -> bool {
        xy.0 >= 0 && xy.1 >= 0 && xy.0 < self.grid.width && xy.1 < self.grid.height
    }

    /// A placed cell's record: the mirror's, or the attempt's own cell once written.
    pub fn placed_rec(&self, cell: &str) -> Option<&'a Placed> {
        if let Some((id, placed)) = self.extra {
            if self.shown && id == cell {
                return Some(placed);
            }
        }
        let rec: &'a Records = self.rec;
        rec.placed.get(cell)
    }

    pub fn placed(&self, cell: &str) -> bool {
        self.placed_rec(cell).is_some()
    }

    /// The placed cells in the world's order, the attempt's own cell last once written.
    pub fn order(&self) -> Vec<String> {
        let mut out = self.rec.order.clone();
        if let Some((id, _)) = self.extra {
            if self.shown && !out.iter().any(|c| c == id) {
                out.push(id.to_string());
            }
        }
        out
    }

    pub fn layer_of(&self, carrier: &str) -> Result<&'a str, Decline> {
        let rec: &'a Records = self.rec;
        rec.carriers
            .get(carrier)
            .map(|c| c.layer.as_str())
            .ok_or_else(|| format!("no carrier {carrier}"))
    }

    pub fn choices(&self, cell: &str, pin: &str) -> &'a [(String, XY, XY)] {
        self.placed_rec(cell)
            .and_then(|c| c.choices.iter().find(|(p, _)| p == pin))
            .map(|(_, v)| v.as_slice())
            .unwrap_or(&[])
    }

    /// The port the pin's wire uses: the recorded one, else a pin's only port.
    pub fn routed_port(&self, cell: &str, pin: &str) -> Option<String> {
        let id = self.rec.pin_id(cell, pin)?;
        let wire = self.wires.get(&self.rec.pins.get(id)?.net)?;
        if let Some((_, port)) = wire.ports.iter().find(|(k, _)| k == id) {
            return Some(port.clone());
        }
        let choices = self.choices(cell, pin);
        (choices.len() == 1).then(|| choices[0].0.clone())
    }

    /// The pin's port in use: the one its wire took, else its first.
    pub fn choice(&self, cell: &str, pin: &str) -> Option<(String, XY, XY)> {
        let choices = self.choices(cell, pin);
        if choices.is_empty() {
            return None;
        }
        let chosen = self.routed_port(cell, pin);
        let found = choices.iter().find(|c| Some(&c.0) == chosen.as_ref());
        Some(found.unwrap_or(&choices[0]).clone())
    }

    /// The ports the pin may still take: in the grid, unused by the cell's other routed pins.
    pub fn open_ports(&self, cell: &str, pin: &str) -> Vec<(String, XY)> {
        let Some(all) = self.placed_rec(cell) else {
            return Vec::new();
        };
        let taken: Set<Option<String>> = all
            .choices
            .iter()
            .filter(|(p, _)| p != pin)
            .map(|(p, _)| self.routed_port(cell, p))
            .collect();
        self.choices(cell, pin)
            .iter()
            .filter(|(port, attach, _)| {
                !taken.contains(&Some(port.clone())) && self.in_grid(*attach)
            })
            .map(|(port, attach, _)| (port.clone(), *attach))
            .collect()
    }

    /// The net's placed pins as terminals, sources first, or the refusal's text.
    pub fn terminals(&self, net: &str) -> Result<Result<Vec<Terminal>, String>, Decline> {
        let n = self.rec.nets.get(net).ok_or("an unknown net")?;
        let (mut out, mut fed, mut takes) = (Vec::new(), n.outside, false);
        for (feeds, refs) in [(true, &n.sources), (false, &n.sinks)] {
            for id in refs {
                let pin = self.rec.pins.get(id).ok_or("an unknown pin")?;
                if !self.placed(&pin.cell) {
                    continue;
                }
                let options = self.open_ports(&pin.cell, &pin.pin);
                if options.is_empty() {
                    return Ok(Err(format!("pin {id} has no open port")));
                }
                out.push(Terminal {
                    id: id.clone(),
                    cell: pin.cell.clone(),
                    at: options[0].1,
                    options,
                    bound: pin.bound,
                    choices: self.choices(&pin.cell, &pin.pin).to_vec(),
                });
                if feeds {
                    fed = true;
                } else {
                    takes = true;
                }
            }
        }
        if !fed {
            return Ok(Err("no placed source feeds it yet".into()));
        }
        if !takes {
            return Ok(Err("no placed sink takes from it yet".into()));
        }
        Ok(Ok(out))
    }

    /// Write the net's placed pins into the attach tables again, after its wire came or went.
    pub fn retable(&mut self, net: &str) {
        for (kind, layer, cell) in self.attach.entries.remove(net).unwrap_or_default() {
            let key = (layer, cell);
            match kind.as_str() {
                "open" => {
                    if self.attach.open.get(&key).is_some_and(|v| v == net) {
                        self.attach.open.remove(&key);
                    }
                }
                "routed" => {
                    if self.attach.routed.get(&key).is_some_and(|v| v == net) {
                        self.attach.routed.remove(&key);
                    }
                }
                _ => {
                    self.attach.ports.remove(&key);
                }
            }
        }
        let wire = self.wires.get(net);
        let held: Set<XY> = wire
            .map(|w| {
                w.segments
                    .iter()
                    .flat_map(|(_, c)| c.iter().cloned())
                    .collect()
            })
            .unwrap_or_default();
        let routed = wire.is_some();
        let mut writes: Vec<(&str, String, XY, XY)> = Vec::new();
        for (cell, pin, layer) in self.attach.pins.get(net).cloned().unwrap_or_default() {
            let count = self.choices(&cell, &pin).len();
            let Some((_, attach, port_cell)) = self.choice(&cell, &pin) else {
                continue;
            };
            if count == 0 {
                continue;
            }
            if routed && held.contains(&attach) {
                writes.push(("routed", layer, attach, port_cell));
            } else if count == 1 {
                writes.push(("open", layer, attach, port_cell));
            }
        }
        let mut written = Vec::new();
        for (kind, layer, attach, port_cell) in writes {
            if kind == "routed" {
                self.attach
                    .routed
                    .insert((layer.clone(), attach), net.to_string());
                self.attach.ports.insert((layer.clone(), attach), port_cell);
                written.push(("routed".to_string(), layer.clone(), attach));
                written.push(("ports".to_string(), layer, attach));
            } else {
                self.attach
                    .open
                    .insert((layer.clone(), attach), net.to_string());
                written.push(("open".to_string(), layer, attach));
            }
        }
        self.attach.entries.insert(net.to_string(), written);
    }

    /// The holder that forbids `occupant` (an occupant key such as `cell:`) on the cell, or None.
    pub fn may_occupy(
        &self,
        layer: &str,
        xy: XY,
        occupant: &str,
    ) -> Result<Option<String>, Decline> {
        for holder in holders(self.grid, layer, xy) {
            let (k, reference) = kind_of(holder);
            let key = match k {
                "reserve" => return Ok(Some(holder.clone())),
                "wire" => {
                    let carrier = self.rec.nets.get(reference).map(|n| n.carrier.as_str());
                    format!("wire:{}", carrier.unwrap_or(""))
                }
                "unit" => {
                    let unit_kind = self.units.get(reference).map(|u| u.kind.as_str());
                    format!("unit:{}", unit_kind.unwrap_or(""))
                }
                _ => "cell:".to_string(),
            };
            let ok = self
                .rec
                .share
                .get(&(key, occupant.to_string()))
                .copied()
                .ok_or("an occupant pair not registered")?;
            if !ok {
                return Ok(Some(holder.clone()));
            }
        }
        Ok(None)
    }

    pub fn next_unit_id(&mut self) -> String {
        self.unit_seq += 1;
        while self.units.contains_key(&format!("u{}", self.unit_seq)) {
            self.unit_seq += 1;
        }
        format!("u{}", self.unit_seq)
    }

    pub fn swept(&self, kind: &str) -> bool {
        self.rec
            .fields
            .as_ref()
            .is_some_and(|f| f.sweeps.iter().any(|s| s.kind == kind))
    }

    /// Hold a unit's cells as `World.place_unit` does: its id, or the refusal and blocking holder.
    pub fn place_unit(
        &mut self,
        kind: &str,
        footprint: &str,
        xy: XY,
        owner: &str,
        id: Option<String>,
    ) -> Result<Result<String, (String, Option<String>)>, Decline> {
        let fp = self
            .rec
            .footprints
            .get(footprint)
            .ok_or("an unknown footprint")?;
        let cells = footprint_cells(xy.0, xy.1, fp.width, fp.height, 0);
        let layers = self.layers_for(footprint)?;
        if !cells.iter().all(|c| self.in_grid(*c)) {
            return Ok(Err(("leaves the grid".to_string(), None)));
        }
        let mine = owner.strip_prefix("net:").unwrap_or(owner);
        let emitter = owner.starts_with("field:") && self.swept(kind);
        let occupant = format!("unit:{kind}");
        for layer in &layers {
            for c in &cells {
                if let Some(o) = self.attach.open.get(&(layer.clone(), *c)) {
                    if o != mine && !emitter {
                        let detail =
                            format!("covers the attach cell {} of a pin of {o}", xy_text(*c));
                        return Ok(Err((detail, None)));
                    }
                }
                if let Some(blocker) = self.may_occupy(layer, *c, &occupant)? {
                    let detail = format!("{blocker} holds {} on {layer}", xy_text(*c));
                    return Ok(Err((detail, Some(blocker))));
                }
            }
        }
        let id = match id {
            Some(id) => id,
            None => self.next_unit_id(),
        };
        self.units.insert(
            id.clone(),
            Unit {
                kind: kind.to_string(),
                footprint: footprint.to_string(),
                x: xy.0,
                y: xy.1,
                rot: 0,
                owner: owner.to_string(),
            },
        );
        let noted = if owner.starts_with("net:") { mine } else { "" };
        self.tables
            .note_unit(&id, footprint, noted, owner.starts_with("field:"));
        let holder = format!("unit:{id}");
        for layer in &layers {
            self.occupy(layer, &cells, &holder);
        }
        Ok(Ok(id))
    }

    /// Place a unit a route needs, moving up to four field emitters aside: its id or the refusal.
    pub fn place(
        &mut self,
        net: &str,
        footprint: &str,
        xy: XY,
        what: &str,
    ) -> Result<Result<String, String>, Decline> {
        let id = self.next_unit_id();
        let owner = format!("net:{net}");
        let mut result = self.place_unit(footprint, footprint, xy, &owner, Some(id.clone()))?;
        let mut gone = 0;
        while gone < 4 {
            let Err((_, Some(holder))) = &result else {
                break;
            };
            let Some(unit) = holder.strip_prefix("unit:") else {
                break;
            };
            if !self
                .units
                .get(unit)
                .is_some_and(|u| u.owner.starts_with("field:"))
            {
                break;
            }
            let unit = unit.to_string();
            gone += 1;
            self.remove_unit(&unit)?;
            result = self.place_unit(footprint, footprint, xy, &owner, Some(id.clone()))?;
        }
        let mut refusal = result.err().map(|(detail, _)| detail);
        if refusal.is_none() && gone > 0 {
            refusal = self.sweep_fields()?.map(|(_, detail)| detail);
        }
        Ok(match refusal {
            Some(detail) => {
                Err(format!("cannot place the {what} {footprint} at {}: {detail}", xy_text(xy)))
            }
            None => Ok(id),
        })
    }

    pub fn has_unit(&self, layer: &str, xy: XY) -> bool {
        holders(self.grid, layer, xy)
            .iter()
            .any(|h| kind_of(h).0 == "unit")
    }

    pub fn unit_at(&self, layer: &str, xy: XY, footprint: &str) -> bool {
        holders(self.grid, layer, xy).iter().any(|h| {
            let (kind, reference) = kind_of(h);
            kind == "unit"
                && self
                    .units
                    .get(reference)
                    .is_some_and(|u| u.footprint == footprint)
        })
    }
}
