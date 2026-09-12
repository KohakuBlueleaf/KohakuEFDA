//! The fields a native pass lays: a square sweep's emitters for every placed cell needing its kind,
//! the coverage the field's emitters reach, and the swept kinds laid afresh as `sweep_fields`
//! lays them.

use super::grid::XY;
use super::hash::{Map, Set};
use super::records::Sweep;
use super::sim::{footprint_cells, Decline, Sim};

impl<'a> Sim<'a> {
    /// The cells a field's emitters reach.
    pub fn coverage(&self, kind: &str) -> Set<XY> {
        let mut out = Set::default();
        let Some(fields) = &self.rec.fields else {
            return out;
        };
        let owner = format!("field:{kind}");
        for u in self.units.values() {
            if u.owner != owner {
                continue;
            }
            if let Some(e) = fields.emitters.iter().find(|e| e.footprint == u.footprint) {
                out.extend(e.offsets.iter().map(|(dx, dy)| (u.x + dx, u.y + dy)));
            }
        }
        out
    }

    pub fn partial(&self, kind: &str) -> bool {
        self.rec
            .fields
            .as_ref()
            .and_then(|f| f.emitters.iter().find(|e| e.kind == kind))
            .is_none_or(|e| e.partial)
    }

    /// Every cell any holder holds on any layer, rows by columns.
    fn used(&self) -> Vec<bool> {
        let (w, h) = (self.grid.width.max(0) as usize, self.grid.height.max(0) as usize);
        let mut out = vec![false; w * h];
        for layer in self.grid.layers.clone() {
            if let Some(map) = self.grid.layer_map(&layer) {
                for (xy, held) in map {
                    if !held.is_empty() && self.in_grid(*xy) {
                        out[xy.1 as usize * w + xy.0 as usize] = true;
                    }
                }
            }
        }
        out
    }

    /// The first anchor in the window, row by row, whose square holds no used cell.
    fn free_anchor(&self, window: (i64, i64, i64, i64), used: &[bool], size: i64) -> Option<XY> {
        let (w, h) = (self.grid.width, self.grid.height);
        let (x1, y1) = (window.2.min(w - size + 1), window.3.min(h - size + 1));
        let (x0, y0) = (window.0.max(0), window.1.max(0));
        if x0 >= x1 || y0 >= y1 {
            return None;
        }
        for y in y0..y1 {
            for x in x0..x1 {
                let free =
                    (0..size).all(|dy| (0..size).all(|dx| !used[((y + dy) * w + x + dx) as usize]));
                if free {
                    return Some((x, y));
                }
            }
        }
        None
    }

    fn placed_rect(&self, cell: &str) -> Option<(i64, i64, i64, i64)> {
        let placed = self.placed_rec(cell)?;
        let fp = self.rec.footprints.get(&placed.footprint)?;
        let cells = footprint_cells(placed.x, placed.y, fp.width, fp.height, placed.rot);
        let x1 = cells.iter().map(|c| c.0).max()? + 1;
        let y1 = cells.iter().map(|c| c.1).max()? + 1;
        Some((placed.x, placed.y, x1, y1))
    }

    /// A square sweep's emitters for the cells needing its kind, as `SquareSweep.cover` lays them.
    fn square_sweep(&self, sweep: &Sweep) -> Result<Vec<XY>, Decline> {
        let area = sweep.area;
        let mut used = self.used();
        let mut rects = Vec::new();
        for cell in &self.order() {
            if self
                .rec
                .needs
                .get(cell)
                .is_some_and(|k| k.contains(&sweep.kind))
            {
                rects.push(
                    self.placed_rect(cell)
                        .ok_or("a placed cell without its rectangle")?,
                );
            }
        }
        rects.sort_by_key(|r| (r.1, r.0));
        let (size, reach) = (sweep.size, sweep.reach);
        let window = |r: (i64, i64, i64, i64)| {
            (
                area.0.max(r.0 - size - reach + 1),
                area.1.max(r.1 - size - reach + 1),
                (area.2 - size + 1).min(r.2 + reach),
                (area.3 - size + 1).min(r.3 + reach),
            )
        };
        let mut groups: Vec<(i64, i64, i64, i64)> = Vec::new();
        for rect in rects {
            let win = window(rect);
            let mut joined = false;
            for shared in groups.iter_mut() {
                let merged = (
                    shared.0.max(win.0),
                    shared.1.max(win.1),
                    shared.2.min(win.2),
                    shared.3.min(win.3),
                );
                if merged.0 < merged.2
                    && merged.1 < merged.3
                    && self.free_anchor(merged, &used, size).is_some()
                {
                    *shared = merged;
                    joined = true;
                    break;
                }
            }
            if !joined && self.free_anchor(win, &used, size).is_some() {
                groups.push(win);
            }
        }
        let w = self.grid.width;
        let mut out = Vec::new();
        for win in groups {
            let Some(spot) = self.free_anchor(win, &used, size) else {
                continue;
            };
            for dy in 0..size {
                for dx in 0..size {
                    used[((spot.1 + dy) * w + spot.0 + dx) as usize] = true;
                }
            }
            out.push(spot);
        }
        Ok(out)
    }

    /// Lay every swept kind afresh as `sweep_fields` does: the refusal's subject and text, or None.
    pub fn sweep_fields(&mut self) -> Result<Option<(String, String)>, Decline> {
        let fields = self
            .rec
            .fields
            .clone()
            .ok_or("fields without a data form")?;
        if fields.sweeps.is_empty() {
            return Ok(None);
        }
        let owners: Set<String> = fields
            .sweeps
            .iter()
            .map(|s| format!("field:{}", s.kind))
            .collect();
        let mut gone: Vec<String> = self
            .units
            .iter()
            .filter(|(_, u)| owners.contains(&u.owner))
            .map(|(id, _)| id.clone())
            .collect();
        gone.sort();
        for id in gone {
            self.remove_unit(&id)?;
        }
        let mut needing: Vec<(String, Vec<XY>, Vec<String>)> = Vec::new();
        for cell in &self.order() {
            let mine: Vec<String> = self
                .rec
                .needs
                .get(cell)
                .map(|k| {
                    k.iter()
                        .filter(|k| fields.sweeps.iter().any(|s| &s.kind == *k))
                        .cloned()
                        .collect()
                })
                .unwrap_or_default();
            if mine.is_empty() {
                continue;
            }
            let placed = self
                .placed_rec(cell)
                .ok_or_else(|| format!("a needing cell not placed: {cell}"))?;
            let fp = self
                .rec
                .footprints
                .get(&placed.footprint)
                .ok_or("an unknown footprint")?;
            let own = footprint_cells(placed.x, placed.y, fp.width, fp.height, placed.rot);
            needing.push((cell.clone(), own, mine));
        }
        let mut spots: Vec<(String, String, XY)> = Vec::new();
        for sweep in &fields.sweeps {
            let found = self.square_sweep(sweep)?;
            if found.is_empty() {
                let cells: Vec<XY> = needing
                    .iter()
                    .filter(|(_, _, m)| m.contains(&sweep.kind))
                    .flat_map(|(_, own, _)| own.iter().cloned())
                    .collect();
                let covered = self.coverage(&sweep.kind);
                let met = if self.partial(&sweep.kind) {
                    cells.iter().any(|c| covered.contains(c))
                } else {
                    cells.iter().all(|c| covered.contains(c))
                };
                if !met {
                    spots.clear();
                    break;
                }
            }
            spots.extend(
                found
                    .into_iter()
                    .map(|xy| (sweep.kind.clone(), sweep.footprint.clone(), xy)),
            );
        }
        for (kind, footprint, xy) in spots {
            let owner = format!("field:{kind}");
            if let Err((detail, _)) = self.place_unit(&kind, &footprint, xy, &owner, None)? {
                return Ok(Some((kind.clone(), format!("cannot place an emitter: {detail}"))));
            }
        }
        let mut coverage: Map<String, Set<XY>> = Map::default();
        for (cell, own, mine) in &needing {
            for kind in mine {
                if !coverage.contains_key(kind) {
                    coverage.insert(kind.clone(), self.coverage(kind));
                }
                let covered = &coverage[kind];
                let hit = if self.partial(kind) {
                    own.iter().any(|c| covered.contains(c))
                } else {
                    own.iter().all(|c| covered.contains(c))
                };
                if !hit {
                    return Ok(Some((
                        cell.clone(),
                        format!("no emitter covers its need for '{kind}'"),
                    )));
                }
            }
        }
        Ok(None)
    }
}
