//! The wire bookkeeping of the simulated world: a wire's runs, a routed wire recorded or taken up
//! with the units only it needed, a unit taken away, and the seed and standing lanes a grow reads.

use std::collections::BTreeMap;

use super::grid::XY;
use super::hash::{Map, Set};
use super::judge::{holders, kind_of};
use super::lanes::{attach_pins, whole_lanes, Pair};
use super::records::Wire;
use super::sim::{footprint_cells, Decline, Sim};
use super::spec::Seed;

fn side(a: XY, b: XY) -> u8 {
    match (b.0 - a.0, b.1 - a.1) {
        (0, -1) => 1,
        (1, 0) => 2,
        (0, 1) => 4,
        (-1, 0) => 8,
        _ => 0,
    }
}

impl<'a> Sim<'a> {
    /// Per layer, the sides the wire continues to on each cell, a used port behind included.
    pub fn runs_of(
        &self,
        net: &str,
        wire: &Wire,
    ) -> Result<BTreeMap<String, Map<XY, u8>>, Decline> {
        let mut out: BTreeMap<String, Map<XY, u8>> = BTreeMap::default();
        for (layer, cells) in &wire.segments {
            let table = out.entry(layer.clone()).or_default();
            for (i, xy) in cells.iter().enumerate() {
                let mut mask = table.get(xy).copied().unwrap_or(0);
                if i > 0 {
                    mask |= side(*xy, cells[i - 1]);
                }
                if i + 1 < cells.len() {
                    mask |= side(*xy, cells[i + 1]);
                }
                table.insert(*xy, mask);
            }
        }
        let n = self.rec.nets.get(net).ok_or("an unknown net")?;
        let layer = self.layer_of(&n.carrier)?;
        let mut bits: Vec<(XY, u8)> = Vec::new();
        if out.get(layer).is_some_and(|t| !t.is_empty()) {
            for id in n.sources.iter().chain(&n.sinks) {
                let pin = self.rec.pins.get(id).ok_or("an unknown pin")?;
                if !self.placed(&pin.cell) {
                    continue;
                }
                if let Some((_, attach, port_cell)) = self.choice(&pin.cell, &pin.pin) {
                    bits.push((attach, side(attach, port_cell)));
                }
            }
        }
        if let Some(table) = out.get_mut(layer) {
            for (attach, bit) in bits {
                if let Some(mask) = table.get_mut(&attach) {
                    *mask |= bit;
                }
            }
        }
        Ok(out)
    }

    pub fn write_runs(
        &mut self,
        holder: &str,
        runs: &BTreeMap<String, Map<XY, u8>>,
        before: &BTreeMap<String, Map<XY, u8>>,
    ) {
        let layers: std::collections::BTreeSet<&String> =
            runs.keys().chain(before.keys()).collect();
        let empty = Map::default();
        for layer in layers {
            let new = runs.get(layer).unwrap_or(&empty);
            let old = before.get(layer).unwrap_or(&empty);
            let cells: Set<XY> = new.keys().chain(old.keys()).cloned().collect();
            let entries: Vec<(XY, u8)> = cells
                .iter()
                .map(|xy| (*xy, new.get(xy).copied().unwrap_or(0)))
                .collect();
            let undo: Vec<(XY, u8)> = cells
                .iter()
                .map(|xy| (*xy, old.get(xy).copied().unwrap_or(0)))
                .collect();
            self.set_runs(layer, holder, &entries, undo);
        }
    }

    /// Record a routed wire: hold its cells, retable its pins, write its runs.
    pub fn set_wire(&mut self, net: &str, wire: Wire) -> Result<(), Decline> {
        let holder = format!("wire:{net}");
        for (layer, cells) in &wire.segments {
            self.occupy(layer, cells, &holder);
        }
        self.wires.insert(net.to_string(), wire.clone());
        self.retable(net);
        let runs = self.runs_of(net, &wire)?;
        self.write_runs(&holder, &runs, &BTreeMap::default());
        Ok(())
    }

    /// Free the net's wire, its units, and the other units that stood only because of it.
    pub fn unroute(&mut self, net: &str) -> Result<(), Decline> {
        let Some(wire) = self.wires.get(net).cloned() else {
            return Ok(());
        };
        let holder = format!("wire:{net}");
        let before = self.runs_of(net, &wire)?;
        self.write_runs(&holder, &BTreeMap::default(), &before);
        let held = self.grid.cells_of(&holder);
        for (layer, cells) in &held {
            self.free(layer, cells, &holder);
        }
        for unit in &wire.units {
            self.remove_unit(unit)?;
        }
        self.wires.remove(net);
        self.retable(net);
        let shared: Vec<String> = held
            .iter()
            .flat_map(|(l, cells)| self.units_on(l, cells))
            .collect();
        self.drop_shared_units(&shared, net)
    }

    /// The units standing on the cells of a layer, cell by cell.
    pub fn units_on(&self, layer: &str, cells: &[XY]) -> Vec<String> {
        cells
            .iter()
            .flat_map(|xy| holders(self.grid, layer, *xy))
            .filter_map(|h| match kind_of(h) {
                ("unit", reference) => Some(reference.to_string()),
                _ => None,
            })
            .collect()
    }

    /// Drop each of the units that stood only because of `net`'s wire.
    pub fn drop_shared_units(&mut self, units: &[String], net: &str) -> Result<(), Decline> {
        for unit in units {
            self.drop_shared_unit(unit, net)?;
        }
        Ok(())
    }

    pub fn drop_shared_unit(&mut self, unit: &str, gone: &str) -> Result<(), Decline> {
        let Some(found) = self.units.get(unit) else {
            return Ok(());
        };
        let Some(other) = found.owner.strip_prefix("net:") else {
            return Ok(());
        };
        if other == gone {
            return Ok(());
        }
        let other = other.to_string();
        let Some(wire) = self.wires.get(&other) else {
            return Ok(());
        };
        if !wire.units.iter().any(|u| u == unit) {
            return Ok(());
        }
        let mut trimmed = wire.clone();
        trimmed.units.retain(|u| u != unit);
        self.remove_unit(unit)?;
        self.wires.insert(other, trimmed);
        Ok(())
    }

    pub fn layers_for(&self, footprint: &str) -> Result<Vec<String>, Decline> {
        let fp = self
            .rec
            .footprints
            .get(footprint)
            .ok_or("an unknown footprint")?;
        let mut out = vec![fp.layer.clone()];
        out.extend(fp.occludes.iter().cloned());
        Ok(out)
    }

    pub fn remove_unit(&mut self, unit: &str) -> Result<(), Decline> {
        let Some(found) = self.units.get(unit).cloned() else {
            return Ok(());
        };
        let fp = self
            .rec
            .footprints
            .get(&found.footprint)
            .ok_or("an unknown footprint")?;
        let cells = footprint_cells(found.x, found.y, fp.width, fp.height, found.rot);
        let holder = format!("unit:{unit}");
        for layer in self.layers_for(&found.footprint)? {
            self.free(&layer, &cells, &holder);
        }
        self.units.remove(unit);
        Ok(())
    }

    /// The seed a routed net gives a grow: its segments, junctions, crossings and ports.
    pub fn seed_of(&self, net: &str) -> Result<Option<Seed>, Decline> {
        let Some(wire) = self.wires.get(net) else {
            return Ok(None);
        };
        let n = self.rec.nets.get(net).ok_or("an unknown net")?;
        let carrier = self
            .rec
            .carriers
            .get(&n.carrier)
            .ok_or("an unknown carrier")?;
        let mut kinds: Vec<(&str, &str)> = Vec::new();
        for (name, fp) in [("split", &carrier.split), ("merge", &carrier.merge)] {
            if let Some(fp) = fp {
                kinds.retain(|(f, _)| *f != fp.as_str());
                kinds.push((fp.as_str(), name));
            }
        }
        let mut junctions: Vec<(XY, String)> = Vec::new();
        for unit in &wire.units {
            let Some(u) = self.units.get(unit) else {
                continue;
            };
            if let Some((_, name)) = kinds.iter().find(|(f, _)| *f == u.footprint) {
                let xy = (u.x, u.y);
                match junctions.iter_mut().find(|(c, _)| *c == xy) {
                    Some(entry) => entry.1 = name.to_string(),
                    None => junctions.push((xy, name.to_string())),
                }
            }
        }
        let layer = self.layer_of(&n.carrier)?;
        let cells: std::collections::BTreeSet<XY> = wire
            .segments
            .iter()
            .flat_map(|(_, c)| c.iter().cloned())
            .collect();
        let mut crossings: Vec<(XY, String, bool)> = Vec::new();
        for xy in cells {
            for h in holders(self.grid, layer, xy) {
                let (kind, reference) = kind_of(h);
                if kind == "wire" && reference != net {
                    crossings.push((xy, reference.to_string(), false));
                    break;
                }
            }
        }
        let own = self.tables.pair(&n.carrier, &n.carrier);
        if own.mode == 2 && !own.unit.is_empty() {
            let seen: Set<XY> = crossings.iter().map(|c| c.0).collect();
            for unit in &wire.units {
                let Some(u) = self.units.get(unit) else {
                    continue;
                };
                if u.footprint != own.unit {
                    continue;
                }
                if !seen.contains(&(u.x, u.y)) {
                    crossings.push(((u.x, u.y), net.to_string(), false));
                }
            }
        }
        Ok(Some(Seed {
            segments: wire.segments.iter().map(|(_, c)| c.clone()).collect(),
            junctions,
            crossings,
            ports: wire.ports.clone(),
        }))
    }

    /// The lanes the net's standing wire carries whole.
    pub fn standing_lanes(&self, net: &str) -> Result<Set<Pair>, Decline> {
        let Some(wire) = self.wires.get(net) else {
            return Ok(Set::default());
        };
        if wire.segments.is_empty() {
            return Ok(Set::default());
        }
        let n = self.rec.nets.get(net).ok_or("an unknown net")?;
        let Ok(found) = self.terminals(net)? else {
            return Ok(Set::default());
        };
        let sources: Set<&str> = n.sources.iter().map(String::as_str).collect();
        let at = attach_pins(&found, &wire.ports);
        let segments: Vec<Vec<XY>> = wire.segments.iter().map(|(_, c)| c.clone()).collect();
        let (_, read) = whole_lanes(segments, &at, &sources);
        Ok(read.into_iter().collect())
    }
}
