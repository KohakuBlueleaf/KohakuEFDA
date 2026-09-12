//! The native placement attempt: `World._place` over the simulated world, from the inspection
//! through the footprint's writes, the pack's legality handed in, the router's pending nets in its
//! order and the routing pass, to the fields laid again; answered as a failed inspection, a refusal
//! with the unit counter, placed or declined, every write undone.

use serde::{Deserialize, Serialize};

use super::grid::{Grid, XY};
use super::hash::Set;
use super::inspect::inspect;
use super::layers::Layers;
use super::records::{Choices, NetOrder, Placed, Records, Sync};
use super::route::{compare, orders, run, Answer as Routing, Costs, Kit, NetPass, Pass, Router};
use super::sim::{footprint_cells, Decline, Sim};
use super::tables::Tables;

/// A candidate placement with the records' sync and the routing settings.
#[derive(Deserialize)]
pub struct Attempt {
    pub sync: Sync,
    pub cell: String,
    pub x: i64,
    pub y: i64,
    pub rot: i64,
    pub footprint: String,
    pub choices: Choices,
    pub legal: Option<(String, String, String)>,
    #[serde(default)]
    pub keys: Vec<(String, String, String)>,
    #[serde(default)]
    pub costs: Costs,
    #[serde(default)]
    pub history: Vec<(String, i64, i64, i64)>,
    #[serde(default)]
    pub float_scale: i64,
}

/// What an attempt answers.
#[derive(Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Outcome {
    Failed {
        failures: Vec<(String, String)>,
    },
    Refused {
        stage: String,
        subject: String,
        detail: String,
        unit_seq: u64,
    },
    Placed,
    Declined {
        why: String,
    },
}

/// The router's order for the nets the placement touches, from each net's order data.
fn net_order(
    sim: &Sim,
    cell: &str,
    pending: &[String],
    grown: &Set<String>,
) -> Result<Vec<String>, Decline> {
    let mut unique: Vec<String> = Vec::new();
    for net in pending {
        if !unique.contains(net) {
            unique.push(net.clone());
        }
    }
    let cell_of = |id: &str| {
        sim.rec
            .pins
            .get(id)
            .map(|p| p.cell.clone())
            .unwrap_or_default()
    };
    let designated = |id: &str| -> Option<XY> {
        let pin = sim.rec.pins.get(id)?;
        sim.choices(&pin.cell, &pin.pin).first().map(|c| c.1)
    };
    let span_of = |a: &str, b: &str| match (designated(a), designated(b)) {
        (Some(p), Some(q)) => (p.0 - q.0).abs() + (p.1 - q.1).abs(),
        _ => 0,
    };
    let mut keyed: Vec<(Vec<(i64, i64)>, String)> = Vec::new();
    for net in unique {
        let data = sim.rec.orders.get(&net).ok_or("a net without its order")?;
        let key = match data {
            NetOrder::Span => vec![(-sim.span(&net), 1)],
            NetOrder::Lanes { key, lanes, rate, tree } => {
                let n = sim.rec.nets.get(&net).ok_or("an unknown net")?;
                let at: Vec<(String, String, (i64, i64))> = lanes
                    .iter()
                    .filter(|(s, t, _)| cell_of(s) == cell || cell_of(t) == cell)
                    .cloned()
                    .collect();
                let mut here = if at.is_empty() { lanes.clone() } else { at };
                let mut rank = 2;
                if let Some(tree) = tree {
                    let rate_of = |id: &String| tree.rates.get(id).copied().unwrap_or(*rate);
                    let joins: Vec<(String, String, (i64, i64))> = n
                        .sources
                        .iter()
                        .filter(|r| cell_of(r) == cell)
                        .map(|r| (r.clone(), tree.main.clone(), rate_of(r)))
                        .collect();
                    let leaves: Vec<(String, String, (i64, i64))> = n
                        .sinks
                        .iter()
                        .filter(|r| cell_of(r) == cell)
                        .map(|r| (tree.root.clone(), r.clone(), rate_of(r)))
                        .collect();
                    if !grown.contains(&net) || (joins.is_empty() && leaves.is_empty()) {
                        rank = 0;
                        here = vec![(tree.root.clone(), tree.main.clone(), rate_of(&tree.root))];
                    } else if !joins.is_empty() {
                        rank = 1;
                        here = joins;
                    } else {
                        rank = 3;
                        here = leaves;
                    }
                }
                let first = here
                    .iter()
                    .map(|(s, t, r)| vec![(-r.0, r.1), (-span_of(s, t), 1)])
                    .min_by(|a, b| compare(a, b))
                    .unwrap_or_else(|| vec![(-rate.0, rate.1), (-sim.span(&net), 1)]);
                let mut k = key.clone();
                k.push((rank, 1));
                k.extend(first);
                k
            }
        };
        keyed.push((key, net));
    }
    keyed.sort_by(|a, b| compare(&a.0, &b.0));
    Ok(keyed.into_iter().map(|(_, n)| n).collect())
}

fn flow(sim: &mut Sim, kit: &mut Kit, doc: &Attempt) -> Result<Outcome, Decline> {
    let fp = sim
        .rec
        .footprints
        .get(&doc.footprint)
        .ok_or("an unknown footprint")?;
    let cells = footprint_cells(doc.x, doc.y, fp.width, fp.height, doc.rot);
    let layers = sim.layers_for(&doc.footprint)?;
    let inspected = inspect(sim, kit, doc, fp, &cells, &layers);
    let (failures, ripped, displaced) = inspected?;
    if !failures.is_empty() {
        return Ok(Outcome::Failed { failures });
    }
    let mut trimmed = Vec::new();
    for net in &ripped {
        if sim.trim(net, &cells)? {
            trimmed.push(net.clone());
        }
    }
    for net in &ripped {
        if !trimmed.contains(net) {
            sim.unroute(net)?;
        }
    }
    for unit in &displaced {
        sim.remove_unit(unit)?;
    }
    let holder = format!("cell:{}", doc.cell);
    for layer in &layers {
        sim.occupy(layer, &cells, &holder);
    }
    sim.shown = true;
    sim.table_cell(&doc.cell)?;
    let refused = |sim: &Sim, stage: &str, subject: String, detail: String| Outcome::Refused {
        stage: stage.to_string(),
        subject,
        detail,
        unit_seq: sim.unit_seq,
    };
    if let Some((stage, subject, detail)) = &doc.legal {
        return Ok(refused(sim, stage, subject.clone(), detail.clone()));
    }
    let nets = sim.nets_of(&doc.cell);
    let mut grown: Vec<String> = trimmed.clone();
    grown.extend(nets.iter().filter(|n| sim.wires.contains_key(*n)).cloned());
    let mut pending: Vec<String> = ripped.clone();
    pending.extend(grown.iter().cloned());
    pending.extend(
        nets.iter()
            .filter(|n| sim.ready(n) && !sim.wires.contains_key(*n))
            .cloned(),
    );
    let grown: Set<String> = grown.into_iter().collect();
    let ordered = net_order(sim, &doc.cell, &pending, &grown)?;
    let pass = Pass {
        sync: Sync::default(),
        nets: ordered.into_iter().map(|net| NetPass { net }).collect(),
        keys: doc.keys.clone(),
        costs: doc.costs.clone(),
        history: doc.history.clone(),
        float_scale: doc.float_scale,
    };
    let (by_net, ranks) = orders(sim, &pass)?;
    let routed = run(&Router { pass: &pass, by_net, ranks }, sim, kit);
    if let Routing::Refused { net, detail, .. } = routed? {
        return Ok(refused(sim, "route", format!("net:{net}"), format!("not routed: {detail}")));
    }
    let swept_now = sim.sweep_fields();
    if let Some((subject, detail)) = swept_now? {
        return Ok(refused(sim, "field", format!("cell:{subject}"), detail));
    }
    let swept: Vec<String> = sim
        .rec
        .fields
        .as_ref()
        .map(|f| f.sweeps.iter().map(|s| s.kind.clone()).collect())
        .unwrap_or_default();
    if sim
        .rec
        .needs
        .get(&doc.cell)
        .is_some_and(|k| k.iter().any(|k| !swept.contains(k)))
    {
        return Err("a need no swept planner covers".into());
    }
    if !displaced.is_empty() {
        if let Some((subject, detail)) = sim.sweep_fields()? {
            return Ok(refused(sim, "field", format!("cell:{subject}"), detail));
        }
    }
    Ok(Outcome::Placed)
}

/// Run one attempt over the grid and undo every write.
pub fn attempt(
    grid: &mut Grid,
    layers: &mut Layers,
    tables: &mut Tables,
    records: &Records,
    kit: &mut Kit,
    doc: &Attempt,
) -> Outcome {
    let placed = Placed {
        x: doc.x,
        y: doc.y,
        rot: doc.rot,
        footprint: doc.footprint.clone(),
        choices: doc.choices.clone(),
    };
    let mut sim = Sim::new(grid, layers, tables, records);
    sim.extra = Some((doc.cell.as_str(), &placed));
    let outcome = flow(&mut sim, kit, doc);
    sim.finish();
    match outcome {
        Ok(outcome) => outcome,
        Err(why) => Outcome::Declined { why },
    }
}
