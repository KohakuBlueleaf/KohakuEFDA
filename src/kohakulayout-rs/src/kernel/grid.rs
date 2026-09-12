//! `Grid`: the same state and the same answers as `PyKernel`, including its `save()` bytes.

use super::hash::{Map, Set};
use std::collections::{BTreeMap, BTreeSet};

pub type XY = (i64, i64);

#[derive(Clone, Debug, Default)]
pub struct Grid {
    pub width: i64,
    pub height: i64,
    pub layers: Vec<String>,
    /// Every layer a write named, the fabric's first; `layers` stays the fabric's.
    names: Vec<String>,
    cells: Vec<Map<XY, Vec<String>>>,
    index: Map<String, Map<String, Set<XY>>>,
    /// Per layer and cell, the sides each wire holder continues to there (`N=1 E=2 S=4 W=8`).
    runs: Vec<Map<XY, Vec<(String, u8)>>>,
}

impl Grid {
    pub fn new(width: i64, height: i64, layers: Vec<String>) -> Grid {
        let count = layers.len();
        Grid {
            width,
            height,
            names: layers.clone(),
            layers,
            cells: vec![Map::default(); count],
            index: Map::default(),
            runs: vec![Map::default(); count],
        }
    }

    fn slot_of(&self, layer: &str) -> Option<usize> {
        self.names.iter().position(|l| l == layer)
    }

    fn slot(&mut self, layer: &str) -> usize {
        match self.slot_of(layer) {
            Some(i) => i,
            None => {
                self.names.push(layer.to_string());
                self.cells.push(Map::default());
                self.runs.push(Map::default());
                self.names.len() - 1
            }
        }
    }

    pub fn occupy(&mut self, layer: &str, cells: &[XY], holder: &str) {
        let i = self.slot(layer);
        if !self.index.contains_key(holder) {
            self.index.insert(holder.to_string(), Map::default());
        }
        let layers = self.index.get_mut(holder).unwrap();
        if !layers.contains_key(layer) {
            layers.insert(layer.to_string(), Set::default());
        }
        let mine = layers.get_mut(layer).unwrap();
        let grid = &mut self.cells[i];
        for xy in cells {
            let held = grid.entry(*xy).or_default();
            if !held.iter().any(|h| h == holder) {
                held.push(holder.to_string());
                held.sort();
            }
            mine.insert(*xy);
        }
    }

    pub fn free(&mut self, layer: &str, cells: &[XY], holder: &str) {
        let i = self.slot(layer);
        let (grid, runs) = (&mut self.cells[i], &mut self.runs[i]);
        let mut mine = self.index.get_mut(holder).and_then(|l| l.get_mut(layer));
        for xy in cells {
            if let Some(at) = runs.get_mut(xy) {
                at.retain(|(h, _)| h != holder);
                if at.is_empty() {
                    runs.remove(xy);
                }
            }
            if let Some(held) = grid.get_mut(xy) {
                held.retain(|h| h != holder);
                if held.is_empty() {
                    grid.remove(xy);
                }
            }
            if let Some(mine) = mine.as_mut() {
                mine.remove(xy);
            }
        }
        let empty = mine.is_some_and(|m| m.is_empty());
        if empty {
            let layers = self.index.get_mut(holder).unwrap();
            layers.remove(layer);
            if layers.is_empty() {
                self.index.remove(holder);
            }
        }
    }

    /// Write the sides a wire holder continues to on each cell; a mask of zero drops the entry.
    pub fn set_runs(&mut self, layer: &str, holder: &str, runs: &[(XY, u8)]) {
        let i = self.slot(layer);
        let table = &mut self.runs[i];
        for (xy, mask) in runs {
            let at = table.entry(*xy).or_default();
            at.retain(|(h, _)| h != holder);
            if *mask != 0 {
                at.push((holder.to_string(), *mask));
                at.sort();
            }
            if at.is_empty() {
                table.remove(xy);
            }
        }
    }

    pub fn run_at(&self, layer: &str, holder: &str, xy: XY) -> u8 {
        self.slot_of(layer)
            .and_then(|i| self.runs[i].get(&xy))
            .and_then(|at| at.iter().find(|(h, _)| h == holder))
            .map(|(_, m)| *m)
            .unwrap_or(0)
    }

    pub fn clear(&mut self) {
        for grid in &mut self.cells {
            grid.clear();
        }
        for runs in &mut self.runs {
            runs.clear();
        }
        self.index.clear();
    }

    pub fn layer_map(&self, layer: &str) -> Option<&Map<XY, Vec<String>>> {
        self.slot_of(layer).map(|i| &self.cells[i])
    }

    pub fn holders_at(&self, layer: &str, xy: XY) -> Vec<String> {
        self.layer_map(layer)
            .and_then(|g| g.get(&xy))
            .cloned()
            .unwrap_or_default()
    }

    pub fn holders(&self, layer: &str, cells: &[XY]) -> Vec<Vec<String>> {
        cells.iter().map(|xy| self.holders_at(layer, *xy)).collect()
    }

    pub fn free_for(&self, layer: &str, cells: &[XY]) -> bool {
        match self.layer_map(layer) {
            Some(g) => cells.iter().all(|xy| !g.contains_key(xy)),
            None => true,
        }
    }

    pub fn cells_of(&self, holder: &str) -> BTreeMap<String, Vec<XY>> {
        self.index
            .get(holder)
            .map(|layers| {
                layers
                    .iter()
                    .map(|(l, cells)| {
                        let mut sorted: Vec<XY> = cells.iter().cloned().collect();
                        sorted.sort();
                        (l.clone(), sorted)
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    pub fn holders_on(&self, layer: &str) -> Vec<String> {
        let mut out: Vec<String> = self
            .index
            .iter()
            .filter(|(_, layers)| layers.get(layer).map(|m| !m.is_empty()).unwrap_or(false))
            .map(|(h, _)| h.clone())
            .collect();
        out.sort();
        out
    }

    pub fn holders_map(&self, layer: &str) -> Vec<(XY, Vec<String>)> {
        let mut out: Vec<(XY, Vec<String>)> = self
            .layer_map(layer)
            .map(|g| g.iter().map(|(xy, held)| (*xy, held.clone())).collect())
            .unwrap_or_default();
        out.sort();
        out
    }

    pub fn extent(
        &self,
        layer: Option<&str>,
        mask: Option<&BTreeSet<XY>>,
    ) -> Option<(i64, i64, i64, i64)> {
        let layers: Vec<&String> = match layer {
            Some(l) => self.layers.iter().filter(|x| x.as_str() == l).collect(),
            None => self.layers.iter().collect(),
        };
        let mut xs = Vec::new();
        let mut ys = Vec::new();
        for name in layers {
            if let Some(g) = self.layer_map(name) {
                for (x, y) in g.keys() {
                    if mask.map(|m| m.contains(&(*x, *y))).unwrap_or(true) {
                        xs.push(*x);
                        ys.push(*y);
                    }
                }
            }
        }
        if xs.is_empty() {
            return None;
        }
        let (min_x, max_x) = (*xs.iter().min().unwrap(), *xs.iter().max().unwrap());
        let (min_y, max_y) = (*ys.iter().min().unwrap(), *ys.iter().max().unwrap());
        Some((min_x, min_y, max_x - min_x + 1, max_y - min_y + 1))
    }

    /// Row-major occupancy flags, `height * width` entries.
    pub fn occupancy(&self, layer: &str) -> Vec<u8> {
        let mut out = vec![0u8; (self.width * self.height).max(0) as usize];
        if let Some(g) = self.layer_map(layer) {
            for (x, y) in g.keys() {
                if *x >= 0 && *y >= 0 && *x < self.width && *y < self.height {
                    out[(y * self.width + x) as usize] = 1;
                }
            }
        }
        out
    }

    /// The same bytes `PyKernel.save` writes: sorted keys, no whitespace.
    pub fn save(&self) -> String {
        let mut out = String::from("{\"height\":");
        out.push_str(&self.height.to_string());
        out.push_str(",\"layers\":{");
        for (i, layer) in self.layers.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push_str(&serde_json::to_string(layer).unwrap());
            out.push_str(":[");
            if let Some(g) = self.layer_map(layer) {
                let mut keys: Vec<&XY> = g.keys().collect();
                keys.sort();
                for (j, xy) in keys.into_iter().enumerate() {
                    let ((x, y), held) = (xy, &g[xy]);
                    if j > 0 {
                        out.push(',');
                    }
                    out.push_str(&format!("[{x},{y},{}]", serde_json::to_string(held).unwrap()));
                }
            }
            out.push(']');
        }
        out.push_str("},\"runs\":{");
        for (i, layer) in self.layers.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push_str(&serde_json::to_string(layer).unwrap());
            out.push_str(":[");
            let mut first = true;
            if let Some(t) = self.slot_of(layer).map(|i| &self.runs[i]) {
                let mut keys: Vec<&XY> = t.keys().collect();
                keys.sort();
                for xy in keys {
                    let ((x, y), at) = (xy, &t[xy]);
                    for (holder, mask) in at {
                        if !first {
                            out.push(',');
                        }
                        first = false;
                        out.push_str(&format!(
                            "[{x},{y},{},{mask}]",
                            serde_json::to_string(holder).unwrap()
                        ));
                    }
                }
            }
            out.push(']');
        }
        out.push_str("},\"width\":");
        out.push_str(&self.width.to_string());
        out.push('}');
        out
    }

    pub fn load(&mut self, blob: &str) -> Result<(), String> {
        let value: serde_json::Value = serde_json::from_str(blob).map_err(|e| e.to_string())?;
        self.clear();
        let layers = value
            .get("layers")
            .and_then(|l| l.as_object())
            .ok_or("no layers")?;
        for (layer, cells) in layers {
            for cell in cells.as_array().ok_or("cells")? {
                let items = cell.as_array().ok_or("cell")?;
                let x = items[0].as_i64().ok_or("x")?;
                let y = items[1].as_i64().ok_or("y")?;
                for holder in items[2].as_array().ok_or("holders")? {
                    self.occupy(layer, &[(x, y)], holder.as_str().ok_or("holder")?);
                }
            }
        }
        if let Some(runs) = value.get("runs").and_then(|r| r.as_object()) {
            for (layer, entries) in runs {
                for entry in entries.as_array().ok_or("runs")? {
                    let items = entry.as_array().ok_or("run")?;
                    let x = items[0].as_i64().ok_or("x")?;
                    let y = items[1].as_i64().ok_or("y")?;
                    let holder = items[2].as_str().ok_or("holder")?;
                    let mask = items[3].as_u64().ok_or("mask")? as u8;
                    self.set_runs(layer, holder, &[((x, y), mask)]);
                }
            }
        }
        Ok(())
    }
}
