//! The inspection before a placement writes anything: the rotation, the region, what the footprint
//! covers and may displace, every pin's port kept open, the other placed pins' ports left open and
//! no unplaced net's attach cell boxed in; and `admits`, its cheap half, over the mirror.

use std::collections::BTreeSet;

use super::attempt::Attempt;
use super::grid::{Grid, XY};
use super::hash::{Map, Set};
use super::judge::{crossable, holders, kind_of};
use super::lanes::xy_text;
use super::layers::Layers;
use super::records::{Footprint, Placed, Records};
use super::route::Kit;
use super::sim::{footprint_cells, Decline, Sim};
use super::tables::Tables;

const POCKET: usize = 12;

pub(super) type Failures = Vec<(String, String)>;

fn same_net(sim: &Sim, net: &str, cell: &str, pin: &str) -> bool {
    sim.rec
        .pin_id(cell, pin)
        .and_then(|id| sim.rec.pins.get(id))
        .is_some_and(|p| p.net == net)
}

fn options<'d>(doc: &'d Attempt, pin: &str) -> &'d [(String, XY, XY)] {
    doc.choices
        .iter()
        .find(|(p, _)| p == pin)
        .map(|(_, v)| v.as_slice())
        .unwrap_or(&[])
}

/// Whether the holder of an attach cell connects the pin instead of shutting it.
#[allow(clippy::too_many_arguments)]
fn connects(
    sim: &Sim,
    kit: &Kit,
    holder: &str,
    attach: XY,
    cell: &str,
    pin: &str,
    carrier: &str,
    layer: &str,
) -> Result<bool, Decline> {
    let (kind, reference) = kind_of(holder);
    match kind {
        "unit" => {
            let unit = sim
                .units
                .get(reference)
                .ok_or("a holder without its unit")?;
            if unit.owner.starts_with("field:") {
                return Ok(true);
            }
            let owner = unit.owner.strip_prefix("net:").unwrap_or(&unit.owner);
            Ok(sim.rec.nets.contains_key(owner)
                && same_net(sim, owner, cell, pin)
                && sim
                    .rec
                    .transfers
                    .contains(&(unit.kind.clone(), carrier.to_string())))
        }
        "wire" => {
            let n = sim
                .rec
                .nets
                .get(reference)
                .ok_or("a wire of an unknown net")?;
            let id = format!("{cell}.{pin}");
            if n.sources.iter().chain(&n.sinks).any(|p| *p == id) {
                return Ok(true);
            }
            crossable(sim.grid, sim.tables, kit.regions, layer, carrier, reference, attach)
                .ok_or_else(|| "a crossing unit not registered".to_string())
        }
        "reserve" => {
            let index = sim
                .tables
                .reservation_index
                .get(reference)
                .ok_or("an unknown reservation")?;
            Ok(sim.tables.reservations[*index as usize] == carrier)
        }
        _ => Ok(false),
    }
}

/// Why the attach cell is closed to the pin, or None.
fn shut_by(
    sim: &Sim,
    kit: &Kit,
    layer: &str,
    attach: XY,
    cell: &str,
    pin: &str,
    carrier: &str,
) -> Result<Option<String>, Decline> {
    let at = xy_text(attach);
    if !sim.in_grid(attach) {
        return Ok(Some(format!("attaches at {at}, outside the grid")));
    }
    if let Some(owner) = sim.attach.open.get(&(layer.to_string(), attach)) {
        if !same_net(sim, owner, cell, pin) {
            return Ok(Some(format!("attaches at {at}, the attach cell of a pin of {owner}")));
        }
    }
    for holder in holders(sim.grid, layer, attach) {
        if !connects(sim, kit, holder, attach, cell, pin, carrier, layer)? {
            return Ok(Some(format!("attaches at {at}, held by {holder}")));
        }
    }
    Ok(None)
}

fn passable(sim: &Sim, layer: &str, xy: XY, net: &str) -> bool {
    let carrier = sim
        .rec
        .nets
        .get(net)
        .map(|n| n.carrier.clone())
        .unwrap_or_default();
    for holder in holders(sim.grid, layer, xy) {
        let (kind, reference) = kind_of(holder);
        if kind == "cell" {
            return false;
        }
        if kind == "wire" && reference != net {
            let other = sim
                .rec
                .nets
                .get(reference)
                .map(|n| n.carrier.as_str())
                .unwrap_or("");
            if sim.tables.pair(&carrier, other).mode == 0 {
                return false;
            }
        }
    }
    true
}

/// Cells reachable from `xy` through passable cells, counted up to the pocket.
fn exits(
    sim: &Sim,
    layer: &str,
    xy: XY,
    mine: &Set<XY>,
    open: &Map<XY, String>,
    net: &str,
) -> usize {
    let mut seen: Set<XY> = Set::from_iter([xy]);
    let mut frontier = vec![xy];
    while !frontier.is_empty() && seen.len() <= POCKET {
        let (cx, cy) = frontier.pop().unwrap_or(xy);
        for (dx, dy) in [(1, 0), (0, 1), (-1, 0), (0, -1)] {
            let next = (cx + dx, cy + dy);
            if seen.contains(&next) || !sim.in_grid(next) || mine.contains(&next) {
                continue;
            }
            if open.get(&next).is_some_and(|o| o != net) {
                continue;
            }
            if passable(sim, layer, next, net) {
                seen.insert(next);
                frontier.push(next);
            }
        }
    }
    seen.len() - 1
}

/// An unplaced net's open attach cells each keep a pocket; the new cell's pins count.
fn boxed(sim: &Sim, doc: &Attempt, mine: &Set<XY>, layers: &[String]) -> Result<Failures, Decline> {
    let mut singles: Vec<(String, XY, String)> = Vec::new();
    let mut own: Vec<((String, String), Vec<XY>)> = Vec::new();
    for (pin, carrier) in sim
        .rec
        .cell_pins
        .get(&doc.cell)
        .cloned()
        .unwrap_or_default()
    {
        let found = options(doc, &pin);
        let net = sim
            .rec
            .pin_id(&doc.cell, &pin)
            .and_then(|id| sim.rec.pins.get(id))
            .map(|p| p.net.clone());
        let Some(net) = net else {
            continue;
        };
        if found.is_empty() {
            continue;
        }
        let layer = sim.layer_of(&carrier)?.to_string();
        if found.len() == 1 {
            singles.push((layer.clone(), found[0].1, net.clone()));
        }
        let attaches: Vec<XY> = found.iter().map(|c| c.1).collect();
        match own.iter_mut().find(|(k, _)| k.0 == layer && k.1 == net) {
            Some(entry) => entry.1 = attaches,
            None => own.push(((layer, net), attaches)),
        }
    }
    let halo: Set<XY> = mine
        .iter()
        .flat_map(|(x, y)| (-1..=1).flat_map(move |dx| (-1..=1).map(move |dy| (x + dx, y + dy))))
        .collect();
    let mut failures = Vec::new();
    for layer in layers {
        let mut layer_open = sim
            .rec
            .open_by_layer
            .get(layer)
            .cloned()
            .unwrap_or_default();
        for (_, xy, net) in singles.iter().filter(|s| &s.0 == layer) {
            match layer_open.iter_mut().find(|(c, _)| c == xy) {
                Some(entry) => entry.1 = net.clone(),
                None => layer_open.push((*xy, net.clone())),
            }
        }
        let open_map: Map<XY, String> = layer_open.iter().cloned().collect();
        let mut pockets: Vec<(String, Vec<XY>)> = layer_open
            .iter()
            .filter(|(xy, net)| {
                halo.contains(xy) && !own.iter().any(|(k, _)| &k.0 == layer && &k.1 == net)
            })
            .map(|(xy, net)| (net.clone(), vec![*xy]))
            .collect();
        pockets.extend(
            own.iter()
                .filter(|(k, _)| &k.0 == layer)
                .map(|(k, c)| (k.1.clone(), c.clone())),
        );
        for (net, cells) in pockets {
            let n = sim.rec.nets.get(&net).ok_or("an unknown net")?;
            let placed = n.sources.iter().chain(&n.sinks).all(|id| {
                sim.rec
                    .pins
                    .get(id)
                    .is_some_and(|p| p.cell == doc.cell || sim.placed(&p.cell))
            });
            if placed {
                continue;
            }
            if cells
                .iter()
                .all(|a| exits(sim, layer, *a, mine, &open_map, &net) < POCKET)
            {
                let detail = format!("boxes in the attach cell {} of {net}", xy_text(cells[0]));
                failures.push(("port_shut".to_string(), detail));
                break;
            }
        }
    }
    Ok(failures)
}

/// Each pin keeps an open port, and every other placed pin keeps one too.
fn port_shut(
    sim: &Sim,
    kit: &Kit,
    doc: &Attempt,
    cells: &[XY],
    layers: &[String],
) -> Result<Failures, Decline> {
    let mut failures = Vec::new();
    for (pin, carrier) in sim
        .rec
        .cell_pins
        .get(&doc.cell)
        .cloned()
        .unwrap_or_default()
    {
        let found = options(doc, &pin);
        if found.is_empty() {
            continue;
        }
        let layer = sim.layer_of(&carrier)?;
        let mut faults = Vec::new();
        for (_, attach, _) in found {
            faults.push(shut_by(sim, kit, layer, *attach, &doc.cell, &pin, &carrier)?);
        }
        if faults.iter().all(Option::is_some) {
            let first = faults[0].clone().unwrap_or_default();
            failures.push(("port_shut".to_string(), format!("pin {pin} {first}")));
        }
    }
    let mine: Set<XY> = cells.iter().cloned().collect();
    failures.extend(boxed(sim, doc, &mine, layers)?);
    let free = |layer: &str, xy: XY| {
        holders(sim.grid, layer, xy)
            .iter()
            .all(|h| kind_of(h).0 != "cell")
    };
    for layer in layers {
        let Some(by_cell) = sim.rec.alternatives.get(layer) else {
            continue;
        };
        let touched: BTreeSet<&(String, String)> = mine
            .iter()
            .filter_map(|xy| by_cell.get(xy))
            .flatten()
            .filter(|(other, _)| *other != doc.cell && sim.placed(other))
            .collect();
        for (other, pin) in touched {
            let open_cells: Vec<XY> = sim
                .open_ports(other, pin)
                .into_iter()
                .map(|(_, a)| a)
                .collect();
            let covered: Vec<XY> = open_cells
                .iter()
                .filter(|a| mine.contains(a))
                .cloned()
                .collect();
            if !covered.is_empty()
                && open_cells
                    .iter()
                    .all(|a| mine.contains(a) || !free(layer, *a))
            {
                let detail = format!("covers {other}.{pin}'s attach cell {}", xy_text(covered[0]));
                failures.push(("port_shut".to_string(), detail));
                break;
            }
        }
    }
    Ok(failures)
}

type Inspected = (Failures, Vec<String>, Vec<String>);

/// Every failure before occupancy, the nets the placement rips and the field emitters it displaces.
pub(super) fn inspect(
    sim: &Sim,
    kit: &Kit,
    doc: &Attempt,
    fp: &Footprint,
    cells: &[XY],
    layers: &[String],
) -> Result<Inspected, Decline> {
    let mut failures: Failures = Vec::new();
    if !fp.rotations.contains(&doc.rot) {
        failures.push(("legal".into(), format!("rotation r{} is not allowed", doc.rot)));
    }
    let in_build = |c: &XY| match &sim.rec.build {
        Some(build) => build.contains(c),
        None => sim.in_grid(*c),
    };
    if !cells.iter().all(|c| sim.in_grid(*c)) {
        failures.push(("region".into(), "leaves the grid".into()));
    } else if !cells.iter().all(in_build) {
        failures.push(("region".into(), "outside the build region".into()));
    }
    let (mut ripped, mut displaced): (Vec<String>, Vec<String>) = (Vec::new(), Vec::new());
    for layer in layers {
        for xy in cells {
            let Some(blocker) = sim.may_occupy(layer, *xy, "cell:")? else {
                continue;
            };
            let (kind, reference) = kind_of(&blocker);
            if let Some(owner) = sim.displaceable(kind, reference) {
                let (what, id) = owner.split_once(':').unwrap_or(("", ""));
                let target = if what == "net" {
                    &mut ripped
                } else {
                    &mut displaced
                };
                if !target.iter().any(|t| t == id) {
                    target.push(id.to_string());
                }
                continue;
            }
            failures
                .push(("overlap".into(), format!("{blocker} holds {} on {layer}", xy_text(*xy))));
            break;
        }
    }
    failures.extend(port_shut(sim, kit, doc, cells, layers)?);
    displaced.retain(|u| sim.units.contains_key(u));
    Ok((failures, ripped, displaced))
}

/// `World.admits` over the mirror: nothing undisplaceable covered and no port shut.
pub fn admits(
    grid: &mut Grid,
    layers: &mut Layers,
    tables: &mut Tables,
    records: &Records,
    kit: &Kit,
    doc: &Attempt,
) -> Result<bool, Decline> {
    let Some(fp) = records.footprints.get(&doc.footprint) else {
        return Ok(false);
    };
    if !fp.rotations.contains(&doc.rot) {
        return Ok(false);
    }
    let placed = Placed {
        x: doc.x,
        y: doc.y,
        rot: doc.rot,
        footprint: doc.footprint.clone(),
        choices: doc.choices.clone(),
    };
    let mut sim = Sim::new(grid, layers, tables, records);
    sim.extra = Some((doc.cell.as_str(), &placed));
    let answer = admitted(&sim, kit, doc, fp);
    sim.finish();
    answer
}

fn admitted(sim: &Sim, kit: &Kit, doc: &Attempt, fp: &Footprint) -> Result<bool, Decline> {
    let cells = footprint_cells(doc.x, doc.y, fp.width, fp.height, doc.rot);
    if !cells.iter().all(|c| sim.in_grid(*c)) {
        return Ok(false);
    }
    let layers = sim.layers_for(&doc.footprint)?;
    for layer in &layers {
        for xy in &cells {
            for holder in holders(sim.grid, layer, *xy) {
                let (kind, reference) = kind_of(holder);
                if sim.displaceable(kind, reference).is_none() {
                    return Ok(false);
                }
            }
        }
    }
    Ok(port_shut(sim, kit, doc, &cells, &layers)?.is_empty())
}
