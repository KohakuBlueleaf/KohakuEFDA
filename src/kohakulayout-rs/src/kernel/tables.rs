//! What every search reads that is no one search's own: the nets with their carriers, each carrier
//! pair's sharing and crossing rule, the crossing units' shapes, the facts of every unit and the
//! carrier of every reservation, registered from Python and versioned so a classification of the
//! layer can be kept while they stand.

use std::collections::BTreeMap;

use super::hash::Map;
use serde::Deserialize;

#[derive(Deserialize, Clone)]
pub struct Shape {
    pub width: i64,
    pub height: i64,
    pub layers: Vec<String>,
}

/// One carrier against another: whether they share a cell, and the crossing mode and unit.
#[derive(Deserialize, Clone, Default)]
pub struct PairRule {
    pub share: bool,
    pub mode: u8,
    pub unit: String,
    pub bent: bool,
}

pub struct UnitFacts {
    pub id: String,
    pub footprint: String,
    pub owner: String,
    pub field: bool,
}

#[derive(Default)]
pub struct Tables {
    pub nets: Vec<String>,
    pub net_index: Map<String, u32>,
    pub carrier_of: Vec<String>,
    pub pairs: Map<String, Map<String, PairRule>>,
    pub shapes: BTreeMap<String, Shape>,
    pub units: Vec<UnitFacts>,
    pub unit_index: Map<String, u32>,
    pub reservations: Vec<String>,
    pub reservation_index: Map<String, u32>,
    /// Counts every change, so classifications and carrier views know when to refresh.
    pub version: u64,
    /// Counts the changes to the nets and the pairs alone, which a carrier's view depends on.
    pub rules_version: u64,
}

impl Tables {
    pub fn set_nets(&mut self, nets: Vec<(String, String)>) {
        self.nets.clear();
        self.net_index.clear();
        self.carrier_of.clear();
        for (net, carrier) in nets {
            self.net_index.insert(net.clone(), self.nets.len() as u32);
            self.nets.push(net);
            self.carrier_of.push(carrier);
        }
        self.version += 1;
        self.rules_version += 1;
    }

    pub fn set_pairs(&mut self, json: &str) -> Result<(), String> {
        self.pairs = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.version += 1;
        self.rules_version += 1;
        Ok(())
    }

    pub fn set_shapes(&mut self, json: &str) -> Result<(), String> {
        self.shapes = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.version += 1;
        Ok(())
    }

    pub fn note_unit(&mut self, id: &str, footprint: &str, owner: &str, field: bool) {
        let facts = UnitFacts {
            id: id.to_string(),
            footprint: footprint.to_string(),
            owner: owner.to_string(),
            field,
        };
        match self.unit_index.get(id) {
            Some(index) => self.units[*index as usize] = facts,
            None => {
                self.unit_index
                    .insert(id.to_string(), self.units.len() as u32);
                self.units.push(facts);
            }
        }
        self.version += 1;
    }

    pub fn set_reservation(&mut self, tag: &str, carrier: &str) {
        match self.reservation_index.get(tag) {
            Some(index) => self.reservations[*index as usize] = carrier.to_string(),
            None => {
                self.reservation_index
                    .insert(tag.to_string(), self.reservations.len() as u32);
                self.reservations.push(carrier.to_string());
            }
        }
        self.version += 1;
    }

    pub fn net(&self, id: &str) -> Option<u32> {
        self.net_index.get(id).copied()
    }

    pub fn pair(&self, carrier: &str, other: &str) -> PairRule {
        self.pairs
            .get(carrier)
            .and_then(|row| row.get(other))
            .cloned()
            .unwrap_or_default()
    }
}

/// One searching carrier's view of every net: sharing and crossing, by net index.
pub struct CarrierView {
    pub share: Vec<bool>,
    pub cross_mode: Vec<u8>,
    pub cross_unit: Vec<String>,
    pub cross_bent: Vec<bool>,
    pub own_mode: u8,
    pub own_unit: String,
}

impl CarrierView {
    pub fn new(carrier: &str, tables: &Tables) -> CarrierView {
        let mut view = CarrierView {
            share: Vec::with_capacity(tables.nets.len()),
            cross_mode: Vec::with_capacity(tables.nets.len()),
            cross_unit: Vec::with_capacity(tables.nets.len()),
            cross_bent: Vec::with_capacity(tables.nets.len()),
            own_mode: 0,
            own_unit: String::new(),
        };
        for other in &tables.carrier_of {
            let rule = tables.pair(carrier, other);
            view.share.push(rule.share);
            view.cross_mode.push(rule.mode);
            view.cross_unit.push(rule.unit);
            view.cross_bent.push(rule.bent);
        }
        let own = tables.pair(carrier, carrier);
        view.own_mode = own.mode;
        view.own_unit = own.unit;
        view
    }
}
