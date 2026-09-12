//! The native routing pass: the lanes a placement made ready, routed over the simulated world as
//! `LaneRouter.route_all` routes them, answered refused, routed or declined, every write undone.

use std::cmp::Ordering;
use std::collections::BTreeSet;
use std::sync::Arc;

use serde::{Deserialize, Serialize};

use super::astar::{Ask, Query, Scratch, View};
use super::grid::{Grid, XY};
use super::hash::Map;
use super::judge::Regions;
use super::lanes::xy_text;
use super::lay::{lay, Answer as Laid};
use super::layers::Layers;
use super::overlay::Overlay;
use super::records::{Key, Records, Sync, Wire};
use super::sim::{Decline, Sim};
use super::spec::{Doc, Policy, Rules};
use super::tables::{CarrierView, Tables};

/// One net the placement touches, in the router's order.
#[derive(Deserialize)]
pub struct NetPass {
    pub net: String,
}

/// Two keys of fractions compared as Python compares tuples of numbers.
pub(super) fn compare(a: &[(i64, i64)], b: &[(i64, i64)]) -> Ordering {
    for (x, y) in a.iter().zip(b) {
        let o = (x.0 as i128 * y.1 as i128).cmp(&(y.0 as i128 * x.1 as i128));
        if o != Ordering::Equal {
            return o;
        }
    }
    a.len().cmp(&b.len())
}

/// The router's costs, the search's rip cost set to the pass's present cost.
#[derive(Deserialize, Default, Clone)]
#[serde(default)]
pub struct Costs {
    pub step: i64,
    pub turn: i64,
    pub crossing: i64,
    pub share: i64,
    pub corridor: i64,
    pub ripup: i64,
    pub displace: i64,
    pub max_steps: i64,
    pub detour: f64,
    pub slack: f64,
}

/// One pass: the sync, the nets in the router's order and the routing settings.
#[derive(Deserialize)]
pub struct Pass {
    pub sync: Sync,
    pub nets: Vec<NetPass>,
    pub keys: Vec<(String, String, String)>,
    pub costs: Costs,
    pub history: Vec<(String, i64, i64, i64)>,
    pub float_scale: i64,
}

/// What a pass answers.
#[derive(Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Answer {
    Refused {
        net: String,
        detail: String,
        unit_seq: u64,
    },
    Routed,
    Declined {
        why: String,
    },
}

/// What a pass reads besides the simulated world.
pub struct Kit<'a> {
    pub scratch: &'a mut Scratch,
    pub walls: &'a Map<String, Arc<Vec<bool>>>,
    pub views: &'a mut Map<(String, u64), Arc<CarrierView>>,
    pub regions: &'a Regions,
}

fn straight(cells: &[XY], index: usize) -> bool {
    if index == 0 || index + 1 >= cells.len() {
        return false;
    }
    let (before, after) = (cells[index - 1], cells[index + 1]);
    before.0 == after.0 || before.1 == after.1
}

pub(super) struct Router<'p> {
    pub(super) pass: &'p Pass,
    pub(super) by_net: Map<String, Policy>,
    pub(super) ranks: Map<String, Vec<Key>>,
}

pub(super) type Orders = (Map<String, Policy>, Map<String, Vec<Key>>);

/// Each net's lanes in the policy's order, with each lane's rank key.
pub(super) fn orders(sim: &Sim, pass: &Pass) -> Result<Orders, Decline> {
    let designated = |id: &str| -> Option<XY> {
        let pin = sim.rec.pins.get(id)?;
        sim.choices(&pin.cell, &pin.pin).first().map(|c| c.1)
    };
    let mut policies = Map::default();
    let mut ranks = Map::default();
    for np in &pass.nets {
        let p = sim
            .rec
            .policies
            .get(&np.net)
            .ok_or("a net without its policy")?;
        let mut lanes: Vec<(usize, &String, &String, Key)> = Vec::new();
        for (i, (s, t, key)) in p.order.iter().enumerate() {
            let span = match (p.span, designated(s), designated(t)) {
                (true, Some(a), Some(b)) => (a.0 - b.0).abs() + (a.1 - b.1).abs(),
                _ => 0,
            };
            let mut lane_key = key.clone();
            if p.span {
                lane_key.push((-span, 1));
            }
            lanes.push((i, s, t, lane_key));
        }
        lanes.sort_by(|a, b| compare(&a.3, &b.3).then(a.0.cmp(&b.0)));
        let rank = lanes
            .iter()
            .map(|(_, _, _, k)| {
                let mut r = p.net_key.clone();
                r.extend(k.iter().cloned());
                if !p.span {
                    r.push((0, 1));
                }
                r
            })
            .collect();
        let policy = Policy {
            lanes: lanes
                .iter()
                .map(|(_, s, t, _)| ((*s).clone(), (*t).clone()))
                .collect(),
            origins: p.origins.clone(),
            blockers: p.blockers.clone(),
            single_joins: p.single_joins,
        };
        policies.insert(np.net.clone(), policy);
        ranks.insert(np.net.clone(), rank);
    }
    Ok((policies, ranks))
}

impl<'p> Router<'p> {
    fn query(&self, sim: &Sim, net: &str, carrier: &str, layer: &str) -> Result<Query, Decline> {
        let (_, walls_key, unit_walls_key) = self
            .pass
            .keys
            .iter()
            .find(|(c, _, _)| c == carrier)
            .ok_or("no walls for the carrier")?;
        let cells = |table: &Overlay<(String, XY), String>| -> Vec<XY> {
            let mut out: Vec<XY> = table
                .iter()
                .filter(|((l, _), owner)| l == layer && *owner != net)
                .map(|((_, xy), _)| *xy)
                .collect();
            out.sort();
            out
        };
        let c = &self.pass.costs;
        Ok(Query {
            net: net.to_string(),
            carrier: carrier.to_string(),
            step: c.step,
            turn: c.turn,
            crossing: c.crossing,
            share: c.share,
            corridor: c.corridor,
            ripup: c.ripup,
            displace: c.displace,
            max_steps: c.max_steps,
            detour: c.detour,
            slack: c.slack,
            allow_rip: false,
            end_on_crossing: false,
            float_scale: self.pass.float_scale,
            protected: BTreeSet::from([net.to_string()]),
            walls: Vec::new(),
            walls_key: walls_key.clone(),
            unit_walls_key: unit_walls_key.clone(),
            shut: cells(&sim.attach.open),
            held: cells(&sim.attach.routed),
            history: self
                .pass
                .history
                .iter()
                .filter(|(l, _, _, _)| l == layer)
                .map(|(_, x, y, n)| (*x, *y, *n))
                .collect(),
        })
    }

    /// Lay the one lane asked for: the plan, or the refusal's text.
    fn plan(
        &self,
        sim: &mut Sim,
        kit: &mut Kit,
        net: &str,
        seed: Option<super::spec::Seed>,
        only: (String, String),
    ) -> Result<Laid, Decline> {
        let n = sim.rec.nets.get(net).ok_or("an unknown net")?;
        if n.outside {
            return Err("a net with an outside edge".into());
        }
        let terminals = sim.terminals(net);
        let found = match terminals? {
            Ok(found) => found,
            Err(detail) => return Ok(Laid::Refused { detail }),
        };
        let carrier = sim
            .rec
            .carriers
            .get(&n.carrier)
            .ok_or("an unknown carrier")?;
        let layer = carrier.layer.clone();
        let policy = self.by_net.get(net).ok_or("a net without its policy")?;
        let doc = Doc {
            net: net.to_string(),
            carrier: n.carrier.clone(),
            layer: layer.clone(),
            sources: n.sources.clone(),
            pins: n.sources.iter().chain(&n.sinks).cloned().collect(),
            terminals: found,
            seed,
            rules: Rules {
                junction: carrier.junction,
                split: carrier.split.clone(),
                merge: carrier.merge.clone(),
            },
            policy: policy.clone(),
            only: Some(only),
        };
        let query = self.query(sim, net, &n.carrier, &layer)?;
        let (w, h) = (sim.grid.width, sim.grid.height);
        let empty = || Arc::new(vec![false; (w.max(0) * h.max(0)) as usize]);
        let walls = kit
            .walls
            .get(&query.walls_key)
            .cloned()
            .unwrap_or_else(empty);
        let unit_walls = kit
            .walls
            .get(&query.unit_walls_key)
            .cloned()
            .unwrap_or_else(empty);
        let view = View::new(query, w, h, walls, unit_walls, sim.tables);
        let key = (n.carrier.clone(), sim.tables.rules_version);
        let carrier_view = match kit.views.get(&key) {
            Some(v) => v.clone(),
            None => {
                let v = Arc::new(CarrierView::new(&n.carrier, sim.tables));
                kit.views.insert(key, v.clone());
                v
            }
        };
        let classified = sim.layers.get(sim.grid, &layer, sim.tables);
        let ask = Ask { view: &view, carrier: &carrier_view, tables: sim.tables, classified };
        lay(sim.grid, sim.tables, kit.regions, &doc, &ask, kit.scratch)
    }

    /// Place the plan's units and the wire: the refusal's text when a unit cannot stand.
    #[allow(clippy::too_many_arguments)]
    fn commit(
        &self,
        sim: &mut Sim,
        net: &str,
        segments: Vec<Vec<XY>>,
        crossings: &[(XY, String, bool)],
        junctions: &[(XY, String)],
        ports: Vec<(String, String)>,
        displaced: &[String],
    ) -> Result<Option<String>, Decline> {
        let n = sim.rec.nets.get(net).ok_or("an unknown net")?;
        let carrier = sim
            .rec
            .carriers
            .get(&n.carrier)
            .ok_or("an unknown carrier")?;
        let layer = carrier.layer.as_str();
        let mut gone: Vec<&String> = displaced
            .iter()
            .filter(|u| sim.units.contains_key(*u))
            .collect();
        gone.sort();
        let mut sorted: Vec<&String> = displaced.iter().collect();
        sorted.sort();
        for unit in sorted {
            sim.remove_unit(unit)?;
        }
        let mut units = Vec::new();
        for (xy, other, reuse) in crossings {
            let other = sim.rec.nets.get(other).ok_or("an unknown net")?;
            let rule = sim.tables.pair(&n.carrier, &other.carrier);
            if rule.mode != 2 || rule.unit.is_empty() {
                continue;
            }
            if *reuse && sim.unit_at(layer, *xy, &rule.unit) {
                continue;
            }
            match sim.place(net, &rule.unit, *xy, "crossing unit")? {
                Ok(id) => units.push(id),
                Err(detail) => return Ok(Some(detail)),
            }
        }
        if carrier.junction == 2 {
            for (xy, what) in junctions {
                let fp = if what == "split" {
                    &carrier.split
                } else {
                    &carrier.merge
                };
                let Some(fp) = fp else {
                    return Ok(Some(format!(
                        "a {what} at {} needs a unit the pack does not declare",
                        xy_text(*xy)
                    )));
                };
                match sim.place(net, fp, *xy, &format!("{what} unit"))? {
                    Ok(id) => units.push(id),
                    Err(detail) => return Ok(Some(detail)),
                }
            }
        }
        if let Some(limit) = carrier.run_limit {
            let limit = limit.max(0) as usize;
            for cells in &segments {
                let mut start = 0usize;
                while start < cells.len() {
                    let end = (start..cells.len())
                        .find(|i| sim.has_unit(layer, cells[*i]))
                        .unwrap_or(cells.len());
                    if end - start <= limit {
                        start = end + 1;
                        continue;
                    }
                    let Some(fp) = &carrier.repeater else {
                        return Ok(Some(format!(
                            "a '{}' run of {} exceeds the limit of {limit} and no repeater exists",
                            n.carrier,
                            end - start
                        )));
                    };
                    let index = (start + 2..start + limit)
                        .rev()
                        .find(|i| straight(cells, *i))
                        .unwrap_or(start + 1);
                    match sim.place(net, fp, cells[index], "repeater")? {
                        Ok(id) => units.push(id),
                        Err(detail) => return Ok(Some(detail)),
                    }
                    start = index + 1;
                }
            }
        }
        let wire = Wire {
            segments: segments
                .into_iter()
                .map(|c| (layer.to_string(), c))
                .collect(),
            units,
            ports,
        };
        sim.set_wire(net, wire)?;
        if !gone.is_empty() {
            if let Some((_, detail)) = sim.sweep_fields()? {
                return Ok(Some(format!("displaced an emitter: {detail}")));
            }
        }
        Ok(None)
    }

    /// Route one lane of a net as `LaneRouter.route` does: the refusal's text, or None.
    fn route(
        &self,
        sim: &mut Sim,
        kit: &mut Kit,
        net: &str,
        only: (String, String),
    ) -> Result<Option<String>, Decline> {
        let policy = self.by_net.get(net).ok_or("a net without its policy")?;
        if !sim.wires.contains_key(net)
            && !policy.lanes.iter().any(|(s, t)| {
                let placed =
                    |id: &String| sim.rec.pins.get(id).is_some_and(|p| sim.placed(&p.cell));
                placed(s) && placed(t)
            })
        {
            return Ok(None);
        }
        let seed = if sim.wires.contains_key(net) {
            let seed = sim.seed_of(net)?;
            sim.unroute(net)?;
            seed
        } else {
            None
        };
        let planned = self.plan(sim, kit, net, seed, only);
        match planned? {
            Laid::Refused { detail, .. } => Ok(Some(detail)),
            Laid::Plan { segments, crossings, junctions, rips, displaced, ports } => {
                if !rips.is_empty() {
                    return Err("a path that rips".into());
                }
                self.commit(sim, net, segments, &crossings, &junctions, ports, &displaced)
            }
        }
    }
}

/// Run one pass: the ready lanes routed in rank order until one is refused; every write undone.
pub fn pass(
    grid: &mut Grid,
    layers: &mut Layers,
    tables: &mut Tables,
    records: &Records,
    kit: &mut Kit,
    pass: &Pass,
) -> Answer {
    let mut sim = Sim::new(grid, layers, tables, records);
    let answer = match orders(&sim, pass) {
        Ok((by_net, ranks)) => run(&Router { pass, by_net, ranks }, &mut sim, kit),
        Err(why) => Err(why),
    };
    sim.finish();
    match answer {
        Ok(answer) => answer,
        Err(why) => Answer::Declined { why },
    }
}

/// A lane waiting to be laid: its rank, its net's place, its place in the net, the net and pins.
type Queued<'r> = (&'r Key, usize, usize, String, String, String);

pub(super) fn run(router: &Router, sim: &mut Sim, kit: &mut Kit) -> Result<Answer, Decline> {
    let mut queue: Vec<Queued> = Vec::new();
    for (position, np) in router.pass.nets.iter().enumerate() {
        let mut standing = sim.standing_lanes(&np.net)?;
        let policy = router
            .by_net
            .get(&np.net)
            .ok_or("a net without its policy")?;
        let ranks = router.ranks.get(&np.net).ok_or("a net without its ranks")?;
        for (i, (s, t)) in policy.lanes.iter().enumerate() {
            if standing.remove(&(Some(s.clone()), Some(t.clone()))) {
                continue;
            }
            let placed = |id: &String| sim.rec.pins.get(id).is_some_and(|p| sim.placed(&p.cell));
            if !placed(s) || !placed(t) {
                continue;
            }
            queue.push((&ranks[i], position, i, np.net.clone(), s.clone(), t.clone()));
        }
    }
    queue.sort_by(|a, b| compare(a.0, b.0).then(a.1.cmp(&b.1)).then(a.2.cmp(&b.2)));
    let queue: Vec<(String, String, String)> = queue.into_iter().map(|q| (q.3, q.4, q.5)).collect();
    for (net, s, t) in queue {
        if let Some(detail) = router.route(sim, kit, &net, (s, t))? {
            return Ok(Answer::Refused { net, detail, unit_seq: sim.unit_seq });
        }
    }
    Ok(Answer::Routed)
}
