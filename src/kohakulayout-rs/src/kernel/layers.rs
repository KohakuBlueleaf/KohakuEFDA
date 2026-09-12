//! The classified layers kept between searches: a layer is classified whole on its first search
//! and after a reset, then only the cells a change touched since are classified again.

use super::astar::Classified;
use super::classify::{classify, classify_cell, Cell};
use super::grid::{Grid, XY};
use super::hash::Map;
use super::tables::Tables;

struct Layer {
    cells: Classified,
    dirty: Vec<usize>,
    full: bool,
    /// While a checkpoint stands: each touched cell's classification before, and the dirty list.
    saved: Option<(Map<usize, Cell>, Vec<usize>)>,
}

/// Every searched layer's classification with the cells changed since it was brought up to date.
#[derive(Default)]
pub struct Layers {
    layers: Map<String, Layer>,
}

impl Layers {
    /// The layer classified for the tables, brought up to date first.
    pub fn get(&mut self, grid: &Grid, layer: &str, tables: &Tables) -> &Classified {
        let w = grid.width.max(0) as usize;
        let entry = self
            .layers
            .entry(layer.to_string())
            .or_insert_with(|| Layer {
                cells: Classified::new(Vec::new()),
                dirty: Vec::new(),
                full: true,
                saved: None,
            });
        if entry.full {
            entry.cells = Classified::new(classify(grid, layer, tables));
            entry.full = false;
            entry.dirty.clear();
        } else if !entry.dirty.is_empty() {
            let map = grid.layer_map(layer);
            for &i in &entry.dirty {
                let xy = ((i % w) as i64, (i / w) as i64);
                let cell = match map.and_then(|m| m.get(&xy)) {
                    Some(held) => classify_cell(grid, layer, tables, xy, held),
                    None => Cell::default(),
                };
                entry.cells.set(i, cell);
            }
            entry.dirty.clear();
        }
        &entry.cells
    }

    /// Note the cells a change touched; too many of them classify the layer whole again.
    pub fn touch(&mut self, layer: &str, cells: &[XY], width: i64, height: i64) {
        let Some(entry) = self.layers.get_mut(layer) else {
            return;
        };
        if entry.full {
            return;
        }
        let (w, h) = (width.max(0) as usize, height.max(0) as usize);
        for (x, y) in cells {
            if *x >= 0 && *y >= 0 && (*x as usize) < w && (*y as usize) < h {
                let i = *y as usize * w + *x as usize;
                if let Some((before, _)) = entry.saved.as_mut() {
                    before
                        .entry(i)
                        .or_insert_with(|| entry.cells.cell(i).clone());
                }
                entry.dirty.push(i);
            }
        }
        if entry.dirty.len() > w * h {
            entry.full = true;
            entry.dirty.clear();
            entry.saved = None;
        }
    }

    /// Classify every layer whole on its next search.
    pub fn reset(&mut self) {
        self.layers.clear();
    }

    /// Start recording touches so `restore` can undo them without classifying again.
    pub fn checkpoint(&mut self) {
        for entry in self.layers.values_mut() {
            if !entry.full {
                entry.saved = Some((Map::default(), entry.dirty.clone()));
            }
        }
    }

    /// Put the classification back as it stood at the checkpoint.
    pub fn restore(&mut self) {
        for entry in self.layers.values_mut() {
            match entry.saved.take() {
                Some((before, dirty)) if !entry.full => {
                    for (i, cell) in before {
                        entry.cells.set(i, cell);
                    }
                    entry.dirty = dirty;
                }
                _ => entry.full = true,
            }
        }
    }
}
