//! The judgements a native lay makes about cells, over the grid and the tables: whether a
//! junction unit may stand on a cell, which of the net's own lane cells another of its lanes may
//! cross, which standing crossings the kept lanes still make, and the one cell a lane without a
//! path stands on. Each answers as its Python twin does; `None` names an unregistered unit.

use std::collections::BTreeSet;

use super::grid::{Grid, XY};
use super::hash::{Map, Set};
use super::spec::Rules;
use super::tables::Tables;

const AXES: [XY; 2] = [(1, 0), (0, 1)];

/// Every region's cells and the regions each unit footprint may stand in.
#[derive(Default)]
pub struct Regions {
    at: Map<XY, Vec<u32>>,
    allowed: Map<String, BTreeSet<u32>>,
    any: bool,
    pub set: bool,
}

impl Regions {
    pub fn register(&mut self, regions: &[(String, Vec<XY>)], allowed: &[(String, Vec<String>)]) {
        let index: Map<&str, u32> = regions
            .iter()
            .enumerate()
            .map(|(i, (id, _))| (id.as_str(), i as u32))
            .collect();
        let mut at: Map<XY, Vec<u32>> = Map::default();
        for (i, (_, cells)) in regions.iter().enumerate() {
            for xy in cells {
                at.entry(*xy).or_default().push(i as u32);
            }
        }
        self.allowed = allowed
            .iter()
            .map(|(fp, ids)| {
                let ok = ids
                    .iter()
                    .filter_map(|r| index.get(r.as_str()).copied())
                    .collect();
                (fp.clone(), ok)
            })
            .collect();
        self.at = at;
        self.any = !regions.is_empty();
        self.set = true;
    }

    /// Whether the unit may stand in every region holding the cell; None for an unknown footprint.
    pub fn unit_allowed(&self, footprint: &str, xy: XY) -> Option<bool> {
        if !self.any {
            return Some(true);
        }
        let ok = self.allowed.get(footprint)?;
        Some(match self.at.get(&xy) {
            Some(hits) => !hits.is_empty() && hits.iter().all(|r| ok.contains(r)),
            None => false,
        })
    }
}

/// The holders of a cell on a layer.
pub fn holders<'a>(grid: &'a Grid, layer: &str, xy: XY) -> &'a [String] {
    grid.layer_map(layer)
        .and_then(|m| m.get(&xy))
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

/// A holder's kind and reference, split at the first colon.
pub fn kind_of(holder: &str) -> (&str, &str) {
    match holder.find(':') {
        Some(i) => (&holder[..i], &holder[i + 1..]),
        None => (holder, ""),
    }
}

fn in_grid(grid: &Grid, xy: XY) -> bool {
    xy.0 >= 0 && xy.1 >= 0 && xy.0 < grid.width && xy.1 < grid.height
}

/// Whether the layers a unit occludes are free at the cell; None for an unknown shape.
pub fn occluded_free(grid: &Grid, tables: &Tables, footprint: &str, xy: XY) -> Option<bool> {
    let shape = tables.shapes.get(footprint)?;
    let cells: Vec<XY> = (0..shape.height)
        .flat_map(|dy| (0..shape.width).map(move |dx| (xy.0 + dx, xy.1 + dy)))
        .collect();
    if !cells.iter().all(|c| in_grid(grid, *c)) {
        return Some(false);
    }
    Some(
        shape
            .layers
            .iter()
            .all(|layer| grid.free_for(layer, &cells)),
    )
}

/// Whether a junction unit could stand on this lane cell.
pub fn may_join(
    grid: &Grid,
    tables: &Tables,
    regions: &Regions,
    rules: &Rules,
    xy: XY,
    layer: &str,
) -> Option<bool> {
    if rules.junction != 2 {
        return Some(true);
    }
    if holders(grid, layer, xy)
        .iter()
        .any(|h| h.starts_with("unit:"))
    {
        return Some(false);
    }
    for fp in [rules.split.as_deref(), rules.merge.as_deref()]
        .into_iter()
        .flatten()
    {
        if !(regions.unit_allowed(fp, xy)? && occluded_free(grid, tables, fp, xy)?) {
            return Some(false);
        }
    }
    Some(true)
}

/// The net's own lane cells another lane may cross, with the lane's axis there (1 across, 2 down).
pub fn crossable_own(
    grid: &Grid,
    layer: &str,
    segments: &[Vec<XY>],
    junctions: &Set<XY>,
    crossed: &Set<XY>,
    behind: &Map<XY, XY>,
) -> Map<XY, u8> {
    let mut out: Map<XY, u8> = Map::default();
    for segment in segments {
        let mut cells = segment.clone();
        if !behind.is_empty() {
            if let Some(b) = behind.get(&cells[0]) {
                cells.insert(0, *b);
            }
            if let Some(b) = behind.get(&cells[cells.len() - 1]) {
                cells.push(*b);
            }
        }
        for i in 1..cells.len().saturating_sub(1) {
            let (before, here, after) = (cells[i - 1], cells[i], cells[i + 1]);
            let axis = if before.0 == after.0 {
                2
            } else if before.1 == after.1 {
                1
            } else {
                continue;
            };
            if junctions.contains(&here) || crossed.contains(&here) || out.contains_key(&here) {
                out.remove(&here);
                continue;
            }
            if !holders(grid, layer, here).is_empty() {
                continue;
            }
            out.insert(here, axis);
        }
    }
    out
}

/// The standing crossings the kept lanes still make.
pub fn standing_crossings(
    grid: &Grid,
    net: &str,
    layer: &str,
    crossings: &[(XY, String, bool)],
    kept: &[Vec<XY>],
) -> Vec<(XY, String, bool)> {
    let mut cover: Map<XY, usize> = Map::default();
    for segment in kept {
        for xy in segment {
            *cover.entry(*xy).or_default() += 1;
        }
    }
    crossings
        .iter()
        .filter(|(xy, other, _)| {
            let n = cover.get(xy).copied().unwrap_or(0);
            if n == 0 {
                return false;
            }
            if other == net {
                return n >= 2;
            }
            let want = format!("wire:{other}");
            holders(grid, layer, *xy).contains(&want)
        })
        .cloned()
        .collect()
}

fn side_bit(d: XY) -> u8 {
    match d {
        (0, -1) => 1,
        (1, 0) => 2,
        (0, 1) => 4,
        (-1, 0) => 8,
        _ => 0,
    }
}

/// Whether the other net's wire crosses a move along `direction` straight; `bent` needs one side.
pub fn straight_through(
    grid: &Grid,
    layer: &str,
    other_net: &str,
    xy: XY,
    direction: XY,
    bent: bool,
) -> bool {
    let run = grid.run_at(layer, &format!("wire:{other_net}"), xy);
    if run == 0 {
        return false;
    }
    let (px, py) = (direction.1, direction.0);
    let side = |dx: i64, dy: i64| run & side_bit((dx, dy)) != 0;
    if bent {
        return side(px, py) || side(-px, -py);
    }
    let across = side(px, py) && side(-px, -py);
    let along = side(direction.0, direction.1) || side(-direction.0, -direction.1);
    across && !along
}

/// Whether a `carrier` wire may cross the other net's wire on the cell.
pub fn crossable(
    grid: &Grid,
    tables: &Tables,
    regions: &Regions,
    layer: &str,
    carrier: &str,
    other_net: &str,
    xy: XY,
) -> Option<bool> {
    let Some(n) = tables.net(other_net) else {
        return Some(false);
    };
    let rule = tables.pair(carrier, &tables.carrier_of[n as usize]);
    if rule.mode == 0 {
        return Some(false);
    }
    if !AXES
        .iter()
        .any(|axis| straight_through(grid, layer, other_net, xy, *axis, rule.bent))
    {
        return Some(false);
    }
    if rule.mode != 2 {
        return Some(true);
    }
    if rule.unit.is_empty() {
        return Some(false);
    }
    if !holders(grid, layer, xy)
        .iter()
        .all(|h| kind_of(h).0 == "wire")
    {
        return Some(false);
    }
    Some(regions.unit_allowed(&rule.unit, xy)? && occluded_free(grid, tables, &rule.unit, xy)?)
}

/// The one cell a pathless lane stands on, crossed if need be; `Some(None)` when all are held.
#[allow(clippy::too_many_arguments)]
pub fn single_cell(
    grid: &Grid,
    tables: &Tables,
    regions: &Regions,
    carrier: &str,
    net: &str,
    layer: &str,
    root: XY,
    cells: &BTreeSet<XY>,
    crossings: &mut Vec<(XY, String, bool)>,
) -> Option<Option<XY>> {
    let mut ordered: Vec<XY> = cells.iter().cloned().collect();
    ordered.sort_by_key(|c| (*c != root, *c));
    let mut foreign: Vec<Vec<String>> = Vec::new();
    for cell in &ordered {
        let here: Vec<String> = holders(grid, layer, *cell)
            .iter()
            .filter_map(|h| {
                let (kind, reference) = kind_of(h);
                (kind == "wire" && reference != net).then(|| reference.to_string())
            })
            .collect();
        if here.is_empty() {
            return Some(Some(*cell));
        }
        foreign.push(here);
    }
    for (cell, here) in ordered.iter().zip(&foreign) {
        if here.len() != 1 {
            continue;
        }
        if crossable(grid, tables, regions, layer, carrier, &here[0], *cell)? {
            crossings.push((*cell, here[0].clone(), false));
            return Some(Some(*cell));
        }
    }
    Some(None)
}
