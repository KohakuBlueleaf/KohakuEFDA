//! Batched physical occupancy queries; traversal order matches the Python fallback.

use super::core::{Grid, GROUND, SKY};

pub type Cell = (i32, i32);
pub type Rect = (i32, i32, i32, i32);

impl Grid {
    pub fn extent_in(&self, area: Rect) -> Option<Rect> {
        let mut result: Option<Rect> = None;
        for y in area.1.max(0)..area.3.min(self.height as i32) {
            for x in area.0.max(0)..area.2.min(self.width as i32) {
                let index = y as usize * self.width + x as usize;
                if self.used(index) {
                    result = Some(match result {
                        None => (x, y, x + 1, y + 1),
                        Some(r) => (r.0.min(x), r.1.min(y), r.2.max(x + 1), r.3.max(y + 1)),
                    });
                }
            }
        }
        result
    }

    pub fn straight_cells(
        &self,
        layer: usize,
        chains: &[Vec<Cell>],
        area: Rect,
    ) -> Vec<(i32, i32, u8)> {
        let mut result = Vec::new();
        let side = &self.layers[layer];
        let ground = &self.layers[GROUND];
        for chain in chains {
            for triple in chain.windows(3) {
                let (before, cell, after) = (triple[0], triple[1], triple[2]);
                if before.0 != after.0 && before.1 != after.1 {
                    continue;
                }
                if cell.0 < area.0 || cell.1 < area.1 || cell.0 >= area.2 || cell.1 >= area.3 {
                    continue;
                }
                let Some(index) = self.index(cell.0, cell.1) else {
                    continue;
                };
                if side.unit[index] || side.count[index] != 1 {
                    continue;
                }
                if layer == SKY && (ground.blocked[index] || ground.count[index] != 0) {
                    continue;
                }
                let direction = match (
                    i64::from(after.0) - i64::from(cell.0),
                    i64::from(after.1) - i64::from(cell.1),
                ) {
                    (0, -1) => 0,
                    (1, 0) => 1,
                    (0, 1) => 2,
                    (-1, 0) => 3,
                    _ => continue,
                };
                result.push((cell.0, cell.1, direction));
            }
        }
        result
    }

    pub fn bridges_outside(&self, layer: usize, cells: &[Cell], area: Rect) -> bool {
        cells.iter().any(|&(x, y)| {
            (x < area.0 || y < area.1 || x >= area.2 || y >= area.3)
                && self
                    .index(x, y)
                    .is_some_and(|i| self.layers[layer].count[i] != 0)
        })
    }
}
