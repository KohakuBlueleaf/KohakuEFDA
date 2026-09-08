//! Netlist lookups and the macro footprint derived from a fragment, as Python does them.

use std::collections::{BTreeMap, BTreeSet};

use super::geometry::{attach_cell, footprint_cells, XY};
use super::model::{Cell, Footprint, Macro, Module, Netlist, Pin, PinRef, Port};

impl Netlist {
    pub fn footprint_for(&self, cell_id: &str) -> Option<&Footprint> {
        let cell = self.cells.get(cell_id)?;
        if let Some(fp) = &cell.footprint {
            return self.library.get(fp);
        }
        if let Some(m) = &cell.macro_ {
            return self.macros.get(m).and_then(|m| m.footprint.as_ref());
        }
        None
    }

    /// Explicit pins, else one pin per port of the footprint or module.
    pub fn pins_of(&self, cell_id: &str) -> Vec<Pin> {
        let Some(cell) = self.cells.get(cell_id) else {
            return Vec::new();
        };
        if !cell.pins.is_empty() {
            return cell.pins.clone();
        }
        if let Some(fp) = self.footprint_for(cell_id) {
            return fp.ports.iter().map(pin_of_port).collect();
        }
        if let Some(module) = cell.module.as_ref().and_then(|m| self.modules.get(m)) {
            return module
                .ports
                .iter()
                .map(|p| Pin {
                    id: p.id.clone(),
                    direction: p.direction.clone(),
                    carrier: p.carrier.clone(),
                    ports: vec![p.id.clone()],
                })
                .collect();
        }
        if let Some(module) = cell
            .macro_
            .as_ref()
            .and_then(|m| self.macros.get(m))
            .and_then(|m| self.modules.get(&m.module))
        {
            return module
                .ports
                .iter()
                .map(|p| Pin {
                    id: p.id.clone(),
                    direction: p.direction.clone(),
                    carrier: p.carrier.clone(),
                    ports: vec![p.id.clone()],
                })
                .collect();
        }
        Vec::new()
    }

    pub fn pin(&self, r: &PinRef) -> Option<Pin> {
        self.pins_of(&r.cell).into_iter().find(|p| p.id == r.pin)
    }

    pub fn is_flat(&self) -> bool {
        !self.cells.values().any(Cell::is_instance)
    }

    /// This netlist seen with a parent's library and definitions behind its own.
    pub fn with_library(&self, parent: &Netlist) -> Netlist {
        let mut out = self.clone();
        let mut library = parent.library.clone();
        library.extend(self.library.clone());
        let mut modules = parent.modules.clone();
        modules.extend(self.modules.clone());
        let mut macros = parent.macros.clone();
        macros.extend(self.macros.clone());
        out.library = library;
        out.modules = modules;
        out.macros = macros;
        out
    }
}

fn pin_of_port(p: &Port) -> Pin {
    Pin {
        id: p.id.clone(),
        direction: p.direction.clone(),
        carrier: p.carrier.clone(),
        ports: vec![p.id.clone()],
    }
}

fn fragment_cells(macro_: &Macro, footprints: &BTreeMap<String, Footprint>) -> BTreeSet<XY> {
    let mut cells = BTreeSet::new();
    for placement in macro_.layout.placements.values() {
        if let Some(fp) = footprints.get(&placement.cell) {
            cells.extend(footprint_cells(
                placement.x,
                placement.y,
                fp.width,
                fp.height,
                placement.rot,
            ));
        }
    }
    for wire in macro_.layout.wires.values() {
        for segment in &wire.segments {
            cells.extend(segment.cells.iter().cloned());
        }
    }
    for unit in macro_.layout.units.values() {
        cells.insert((unit.x, unit.y));
    }
    cells
}

/// The macro's footprint from its fragment, or the problems that prevent one; Python's `derive_footprint`.
pub fn derive_footprint(
    macro_: &Macro,
    module: &Module,
    footprints: &BTreeMap<String, Footprint>,
    pins: &BTreeMap<String, BTreeMap<String, Vec<String>>>,
) -> (Option<Footprint>, Vec<String>) {
    let cells = fragment_cells(macro_, footprints);
    let mut problems = Vec::new();
    let where_ = format!("macro {}", macro_.id);
    if cells.is_empty() {
        return (None, vec![format!("{where_}: the fragment places nothing")]);
    }
    let min_x = cells.iter().map(|c| c.0).min().unwrap();
    let min_y = cells.iter().map(|c| c.1).min().unwrap();
    if (min_x, min_y) != (0, 0) {
        problems.push(format!(
            "{where_}: the fragment's top-left corner is ({min_x},{min_y}), not (0,0)"
        ));
    }
    let width = cells.iter().map(|c| c.0).max().unwrap() + 1;
    let height = cells.iter().map(|c| c.1).max().unwrap() + 1;
    let mut ports = Vec::new();
    let mut layers: BTreeSet<String> = BTreeSet::new();
    for placement in macro_.layout.placements.values() {
        if let Some(fp) = footprints.get(&placement.cell) {
            layers.insert(fp.layer.clone());
            layers.extend(fp.occludes.iter().cloned());
        }
    }
    for mport in &module.ports {
        let placement = macro_.layout.placements.get(&mport.inner.cell);
        let fp = footprints.get(&mport.inner.cell);
        let allowed = pins
            .get(&mport.inner.cell)
            .and_then(|m| m.get(&mport.inner.pin))
            .cloned()
            .unwrap_or_default();
        let (Some(placement), Some(fp)) = (placement, fp) else {
            problems.push(format!(
                "{where_}: port {:?} binds to an unplaced or unknown pin {}",
                mport.id,
                mport.inner.text()
            ));
            continue;
        };
        if allowed.is_empty() {
            problems.push(format!(
                "{where_}: port {:?} binds to an unplaced or unknown pin {}",
                mport.id,
                mport.inner.text()
            ));
            continue;
        }
        let Some(port) = fp.port(&allowed[0]) else {
            problems.push(format!(
                "{where_}: port {:?} names a missing port {:?}",
                mport.id, allowed[0]
            ));
            continue;
        };
        let (ax, ay) = attach_cell(fp.width, fp.height, &port.side, port.offset, placement.rot);
        let (ax, ay) = (ax + placement.x, ay + placement.y);
        let (side, offset) = if ay == -1 && (0..width).contains(&ax) {
            ("N", ax)
        } else if ay == height && (0..width).contains(&ax) {
            ("S", ax)
        } else if ax == -1 && (0..height).contains(&ay) {
            ("W", ay)
        } else if ax == width && (0..height).contains(&ay) {
            ("E", ay)
        } else {
            problems.push(format!("{where_}: port {:?} does not reach the macro's edge", mport.id));
            continue;
        };
        ports.push(Port {
            id: mport.id.clone(),
            side: side.to_string(),
            offset,
            direction: mport.direction.clone(),
            carrier: mport.carrier.clone(),
            attrs: BTreeMap::new(),
        });
    }
    if !problems.is_empty() {
        return (None, problems);
    }
    let layer = if layers.contains("ground") || layers.is_empty() {
        "ground".to_string()
    } else {
        layers.iter().next().unwrap().clone()
    };
    let occludes: Vec<String> = layers.iter().filter(|l| **l != layer).cloned().collect();
    (
        Some(Footprint {
            id: macro_.id.clone(),
            width,
            height,
            layer,
            occludes,
            rotations: super::geometry::ROTATIONS.to_vec(),
            ports,
            attrs: BTreeMap::new(),
        }),
        Vec::new(),
    )
}
