//! `Grid`: the same state and the same answers as `PyKernel`, including its `save()` bytes.

use std::collections::{BTreeMap, BTreeSet};

pub type XY = (i64, i64);

#[derive(Clone, Debug, Default)]
pub struct Grid {
    pub width: i64,
    pub height: i64,
    pub layers: Vec<String>,
    grid: BTreeMap<String, BTreeMap<XY, Vec<String>>>,
    index: BTreeMap<String, BTreeMap<String, BTreeSet<XY>>>,
}

impl Grid {
    pub fn new(width: i64, height: i64, layers: Vec<String>) -> Grid {
        let grid = layers
            .iter()
            .map(|l| (l.clone(), BTreeMap::new()))
            .collect();
        Grid { width, height, layers, grid, index: BTreeMap::new() }
    }

    pub fn occupy(&mut self, layer: &str, cells: &[XY], holder: &str) {
        let grid = self.grid.entry(layer.to_string()).or_default();
        let mine = self
            .index
            .entry(holder.to_string())
            .or_default()
            .entry(layer.to_string())
            .or_default();
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
        let grid = self.grid.entry(layer.to_string()).or_default();
        for xy in cells {
            if let Some(held) = grid.get_mut(xy) {
                held.retain(|h| h != holder);
                if held.is_empty() {
                    grid.remove(xy);
                }
            }
            if let Some(layers) = self.index.get_mut(holder) {
                if let Some(mine) = layers.get_mut(layer) {
                    mine.remove(xy);
                }
            }
        }
        let empty = self
            .index
            .get(holder)
            .and_then(|l| l.get(layer))
            .map(|m| m.is_empty())
            .unwrap_or(false);
        if empty {
            let layers = self.index.get_mut(holder).unwrap();
            layers.remove(layer);
            if layers.is_empty() {
                self.index.remove(holder);
            }
        }
    }

    pub fn clear(&mut self) {
        for grid in self.grid.values_mut() {
            grid.clear();
        }
        self.index.clear();
    }

    pub fn holders_at(&self, layer: &str, xy: XY) -> Vec<String> {
        self.grid
            .get(layer)
            .and_then(|g| g.get(&xy))
            .cloned()
            .unwrap_or_default()
    }

    pub fn holders(&self, layer: &str, cells: &[XY]) -> Vec<Vec<String>> {
        cells.iter().map(|xy| self.holders_at(layer, *xy)).collect()
    }

    pub fn free_for(&self, layer: &str, cells: &[XY]) -> bool {
        match self.grid.get(layer) {
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
                    .map(|(l, cells)| (l.clone(), cells.iter().cloned().collect()))
                    .collect()
            })
            .unwrap_or_default()
    }

    pub fn holders_on(&self, layer: &str) -> Vec<String> {
        self.index
            .iter()
            .filter(|(_, layers)| layers.get(layer).map(|m| !m.is_empty()).unwrap_or(false))
            .map(|(h, _)| h.clone())
            .collect()
    }

    pub fn holders_map(&self, layer: &str) -> Vec<(XY, Vec<String>)> {
        self.grid
            .get(layer)
            .map(|g| g.iter().map(|(xy, held)| (*xy, held.clone())).collect())
            .unwrap_or_default()
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
            if let Some(g) = self.grid.get(name) {
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
        if let Some(g) = self.grid.get(layer) {
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
            if let Some(g) = self.grid.get(layer) {
                for (j, ((x, y), held)) in g.iter().enumerate() {
                    if j > 0 {
                        out.push(',');
                    }
                    out.push_str(&format!("[{x},{y},{}]", serde_json::to_string(held).unwrap()));
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
        Ok(())
    }
}
