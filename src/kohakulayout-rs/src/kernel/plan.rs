//! The plan a native lay builds and the questions its worklist asks of it: where a lane may
//! start or end at a pin, which cells stand for a junction, what the policy's origins and blockers
//! answer, and what taking up standing lanes leaves.

use std::collections::BTreeSet;

use super::grid::{Grid, XY};
use super::hash::{Map, Set};
use super::judge::{crossable_own, may_join, standing_crossings, Regions};
use super::lanes::{attach_pins, get, laid_enough, put, trunk_index, whole_lanes, Lane, Pair};
use super::spec::{Blockers, Doc, Origins, Terminal};
use super::tables::Tables;

pub(super) struct Lay<'a> {
    pub(super) doc: &'a Doc,
    pub(super) grid: &'a Grid,
    pub(super) tables: &'a Tables,
    pub(super) regions: &'a Regions,
    pub(super) by_ref: Map<&'a str, &'a Terminal>,
    pub(super) port_at: Map<(&'a str, XY), &'a str>,
    pub(super) at: Map<XY, String>,
    pub(super) behind: Map<XY, XY>,
    pub(super) sources: Set<&'a str>,
    pub(super) seed_junctions: Map<XY, &'a str>,
    pub(super) seed_crossings: Vec<(XY, String, bool)>,
    pub(super) seed_ports: Vec<(String, String)>,
    pub(super) standing: Map<XY, bool>,
    pub(super) segments: Vec<Vec<XY>>,
    pub(super) pins: Vec<Pair>,
    pub(super) crossings: Vec<(XY, String, bool)>,
    pub(super) junctions: Vec<(XY, String)>,
    pub(super) rips: BTreeSet<String>,
    pub(super) displaced: BTreeSet<String>,
    pub(super) ports: Vec<(String, String)>,
    pub(super) sat: Map<XY, BTreeSet<String>>,
    pub(super) crossed: Set<XY>,
}

impl<'a> Lay<'a> {
    pub(super) fn new(
        doc: &'a Doc,
        grid: &'a Grid,
        tables: &'a Tables,
        regions: &'a Regions,
    ) -> Lay<'a> {
        let mut port_at = Map::default();
        for t in &doc.terminals {
            for (port, attach) in &t.options {
                port_at.insert((t.id.as_str(), *attach), port.as_str());
            }
        }
        let seed_ports = doc
            .seed
            .as_ref()
            .map(|s| s.ports.clone())
            .unwrap_or_default();
        let mut behind = Map::default();
        for t in &doc.terminals {
            let recorded = get(&seed_ports, &t.id);
            for (port, attach, port_cell) in &t.choices {
                if t.bound || Some(port.as_str()) == recorded {
                    behind.insert(*attach, *port_cell);
                }
            }
        }
        Lay {
            doc,
            grid,
            tables,
            regions,
            by_ref: doc.terminals.iter().map(|t| (t.id.as_str(), t)).collect(),
            port_at,
            at: attach_pins(&doc.terminals, &seed_ports),
            behind,
            sources: doc.sources.iter().map(String::as_str).collect(),
            seed_junctions: doc
                .seed
                .iter()
                .flat_map(|s| s.junctions.iter().map(|(xy, k)| (*xy, k.as_str())))
                .collect(),
            seed_crossings: doc
                .seed
                .as_ref()
                .map(|s| s.crossings.clone())
                .unwrap_or_default(),
            seed_ports,
            standing: Map::default(),
            segments: Vec::new(),
            pins: Vec::new(),
            crossings: Vec::new(),
            junctions: Vec::new(),
            rips: BTreeSet::default(),
            displaced: BTreeSet::default(),
            ports: Vec::new(),
            sat: Map::default(),
            crossed: Set::default(),
        }
    }

    pub(super) fn junction(&self, xy: XY) -> Option<&str> {
        self.junctions
            .iter()
            .find(|(c, _)| *c == xy)
            .map(|(_, k)| k.as_str())
    }

    pub(super) fn set_junction(&mut self, xy: XY, kind: &str) {
        match self.junctions.iter_mut().find(|(c, _)| *c == xy) {
            Some(entry) => entry.1 = kind.to_string(),
            None => self.junctions.push((xy, kind.to_string())),
        }
    }

    pub(super) fn junction_cells(&self) -> Set<XY> {
        self.junctions.iter().map(|(c, _)| *c).collect()
    }

    pub(super) fn has_pin(&self, source: &str, sink: &str) -> bool {
        self.pins
            .iter()
            .any(|(s, t)| s.as_deref() == Some(source) && t.as_deref() == Some(sink))
    }

    pub(super) fn took(&mut self, t: &'a Terminal, cell: XY) -> Result<(), String> {
        self.sat.entry(cell).or_default().insert(t.cell.clone());
        if !t.bound {
            let port = self
                .port_at
                .get(&(t.id.as_str(), cell))
                .copied()
                .ok_or("an attach cell without its port")?;
            put(&mut self.ports, &t.id, port);
        }
        Ok(())
    }

    /// Start the plan again from the standing segments that still read as whole lanes.
    pub(super) fn absorb(&mut self, segments: Vec<Vec<XY>>) -> Result<(), String> {
        let (kept, read) = whole_lanes(segments, &self.at, &self.sources);
        self.crossings = standing_crossings(
            self.grid,
            &self.doc.net,
            &self.doc.layer,
            &self.seed_crossings,
            &kept,
        );
        self.ports = self.seed_ports.clone();
        self.junctions.clear();
        let mut holding: Map<XY, usize> = Map::default();
        for segment in &kept {
            let unique: Set<XY> = segment.iter().cloned().collect();
            for c in unique {
                *holding.entry(c).or_default() += 1;
            }
        }
        for segment in &kept {
            let elsewhere = |c: &XY| {
                let own = usize::from(segment.contains(c));
                holding.get(c).copied().unwrap_or(0) > own
            };
            let (head, tail) = (segment[0], segment[segment.len() - 1]);
            if elsewhere(&head) && self.seed_junctions.get(&head).copied() == Some("split") {
                self.set_junction(head, "split");
            }
            if elsewhere(&tail) && self.seed_junctions.get(&tail).copied() == Some("merge") {
                self.set_junction(tail, "merge");
            }
        }
        self.sat.clear();
        for (segment, (source, sink)) in kept.iter().zip(&read) {
            let ends = [(source, segment[0]), (sink, segment[segment.len() - 1])];
            for (reference, cell) in ends {
                let Some(reference) = reference else {
                    continue;
                };
                let Some(t) = self.by_ref.get(reference.as_str()).copied() else {
                    continue;
                };
                if t.options.iter().any(|(_, a)| *a == cell) {
                    self.took(t, cell)?;
                }
            }
        }
        self.segments = kept;
        self.pins = read;
        self.crossed = self.crossings.iter().map(|(xy, _, _)| *xy).collect();
        Ok(())
    }

    pub(super) fn stands(&mut self, cell: XY) -> Result<bool, String> {
        if self.crossed.contains(&cell) || self.junction(cell).is_some() {
            return Ok(false);
        }
        if let Some(found) = self.standing.get(&cell) {
            return Ok(*found);
        }
        let found =
            may_join(self.grid, self.tables, self.regions, &self.doc.rules, cell, &self.doc.layer)
                .ok_or("a junction unit not registered")?;
        self.standing.insert(cell, found);
        Ok(found)
    }

    pub(super) fn open_for(&self, t: &Terminal) -> Vec<XY> {
        t.options
            .iter()
            .map(|(_, a)| *a)
            .filter(|a| !self.sat.get(a).is_some_and(|cells| cells.contains(&t.cell)))
            .collect()
    }

    /// The port cell behind each placed pin's attach cell, through the recorded port or every port.
    pub(super) fn port_cells_behind(&self) -> Map<XY, XY> {
        let mut out = Map::default();
        for pin in &self.doc.pins {
            let Some(t) = self.by_ref.get(pin.as_str()) else {
                continue;
            };
            let chosen = get(&self.ports, pin);
            for (port, attach, port_cell) in &t.choices {
                if chosen.is_none() || chosen == Some(port.as_str()) {
                    out.insert(*attach, *port_cell);
                }
            }
        }
        out
    }

    /// The straight cells of the pin's lanes long enough to join, the trunk cut on a tree.
    pub(super) fn straight_origins(
        &self,
        mine: &[usize],
        joinable: Set<XY>,
        merging: bool,
        min_own: usize,
        trunk: Option<&(String, String)>,
    ) -> Set<XY> {
        let segments: Vec<Vec<XY>> = mine.iter().map(|i| self.segments[*i].clone()).collect();
        if segments.is_empty() {
            return joinable;
        }
        let long = laid_enough(&segments, min_own);
        let lanes: Vec<&Pair> = mine.iter().map(|i| &self.pins[*i]).collect();
        let at = trunk.and_then(|(root, main)| trunk_index(&lanes, root, main));
        let behind = self.port_cells_behind();
        let mut runs: Vec<Vec<XY>> = Vec::new();
        match at {
            None => runs.extend(
                segments
                    .iter()
                    .zip(&long)
                    .filter(|(_, k)| **k)
                    .map(|(r, _)| r.clone()),
            ),
            Some(at) => {
                let trunk_run = &segments[at];
                let laid: &[Vec<XY>] = if self.segments.is_empty() {
                    &segments
                } else {
                    &self.segments
                };
                let before = laid.iter().position(|r| r == trunk_run).unwrap_or(at);
                let earlier: Set<XY> = laid[..before].iter().flatten().cloned().collect();
                let (head, tail) = (trunk_run[0], trunk_run[trunk_run.len() - 1]);
                let first = usize::from(!behind.contains_key(&head) || earlier.contains(&head));
                let last = if !behind.contains_key(&tail) || earlier.contains(&tail) {
                    trunk_run.len() - 1
                } else {
                    trunk_run.len()
                };
                if long[at] {
                    if merging {
                        let stop = (0..trunk_run.len())
                            .find(|i| *i >= first && self.junction(trunk_run[*i]) == Some("split"))
                            .unwrap_or(trunk_run.len());
                        runs.push(trunk_run[..(stop + 1).min(trunk_run.len())].to_vec());
                    } else {
                        let start = (0..trunk_run.len())
                            .rev()
                            .find(|i| *i < last && self.junction(trunk_run[*i]) == Some("merge"))
                            .unwrap_or(0);
                        runs.push(trunk_run[start..].to_vec());
                    }
                }
                runs.extend(
                    segments
                        .iter()
                        .zip(&long)
                        .enumerate()
                        .filter(|(i, (_, k))| **k && *i != at)
                        .map(|(_, (r, _))| r.clone()),
                );
            }
        }
        let mut straight = Set::default();
        for mut run in runs {
            if let Some(b) = behind.get(&run[0]) {
                run.insert(0, *b);
            }
            if let Some(b) = behind.get(&run[run.len() - 1]) {
                run.push(*b);
            }
            for i in 1..run.len().saturating_sub(1) {
                if run[i - 1].0 == run[i + 1].0 || run[i - 1].1 == run[i + 1].1 {
                    straight.insert(run[i]);
                }
            }
        }
        joinable
            .into_iter()
            .filter(|c| straight.contains(c))
            .collect()
    }

    /// Where a lane may start (side 0) or end (side 1) at this pin, with the pin's own lane cells.
    pub(super) fn ends(
        &mut self,
        t: &'a Terminal,
        side: usize,
    ) -> Result<(Vec<XY>, Set<XY>), String> {
        let mine: Vec<usize> = self
            .pins
            .iter()
            .enumerate()
            .filter(|(_, p)| {
                (if side == 0 { &p.0 } else { &p.1 }).as_deref() == Some(t.id.as_str())
            })
            .map(|(i, _)| i)
            .collect();
        if mine.is_empty() {
            let held: Set<XY> = self.segments.iter().flatten().cloned().collect();
            let crossable = crossable_own(
                self.grid,
                &self.doc.layer,
                &self.segments,
                &self.junction_cells(),
                &self.crossed,
                &self.behind,
            );
            let open = self
                .open_for(t)
                .into_iter()
                .filter(|c| !held.contains(c) || crossable.contains_key(c))
                .collect();
            return Ok((open, Set::default()));
        }
        let cells: Set<XY> = mine
            .iter()
            .flat_map(|i| self.segments[*i].iter().cloned())
            .collect();
        let mut joinable = Set::default();
        for c in &cells {
            if self.stands(*c)? {
                joinable.insert(*c);
            }
        }
        let allowed = match &self.doc.policy.origins {
            Origins::All => joinable,
            Origins::Straight { min_own, trunk } => {
                self.straight_origins(&mine, joinable, side == 1, *min_own, trunk.as_ref())
            }
        };
        let mut ordered = Vec::new();
        let mut seen = Set::default();
        for i in &mine {
            for c in &self.segments[*i] {
                if allowed.contains(c) && seen.insert(*c) {
                    ordered.push(*c);
                }
            }
        }
        Ok((ordered, cells))
    }

    /// The standing lanes a lane with nowhere to start or end takes up on a tree.
    pub(super) fn blockers(&self, source: &str, sink: &str) -> Result<Vec<Lane>, String> {
        let Blockers::Trunk { root, main } = &self.doc.policy.blockers else {
            return Ok(Vec::new());
        };
        let at = if self.pins.is_empty() {
            0
        } else {
            let found = self.pins.iter().position(|(s, t)| {
                s.as_deref() == Some(root.as_str()) && t.as_deref() == Some(main.as_str())
            });
            match found {
                Some(i) => i,
                None => return Ok(Vec::new()),
            }
        };
        let joining = sink == main && source != root;
        let branching = source == root && sink != main;
        if !(joining || branching) {
            return Ok(Vec::new());
        }
        let trunk: Set<XY> = self
            .segments
            .get(at)
            .ok_or("a trunk past the lanes")?
            .iter()
            .cloned()
            .collect();
        let mut out = Vec::new();
        for (i, (segment, (s, t))) in self.segments.iter().zip(&self.pins).enumerate() {
            if i == at {
                continue;
            }
            let (Some(s), Some(t)) = (s, t) else {
                continue;
            };
            let leaves = s == root && t != main && trunk.contains(&segment[0]);
            let joins = t == main && s != root && trunk.contains(&segment[segment.len() - 1]);
            if (joining && leaves) || (branching && joins) {
                out.push((s.clone(), t.clone()));
            }
        }
        Ok(out)
    }
}
