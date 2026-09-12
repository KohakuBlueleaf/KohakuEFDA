//! What a native attempt does before routing: what the footprint may displace, the trims of the
//! wires under it, the cell's pins written into the attach tables, and the nets it leaves ready.

use std::collections::BTreeSet;

use super::grid::XY;
use super::hash::Set;
use super::records::Wire;
use super::sim::{Decline, Sim};

impl<'a> Sim<'a> {
    /// What a footprint may push out of a cell: `net:<id>` or `unit:<id>`; None for anything else.
    pub fn displaceable(&self, kind: &str, reference: &str) -> Option<String> {
        match kind {
            "wire" => Some(format!("net:{reference}")),
            "unit" => {
                let unit = self.units.get(reference)?;
                if unit.owner.starts_with("field:") {
                    Some(format!("unit:{reference}"))
                } else if unit.owner.starts_with("net:") {
                    Some(unit.owner.clone())
                } else {
                    None
                }
            }
            _ => None,
        }
    }

    /// The attach cell of a pin's recorded port, from its `cell.pin` key.
    fn attach_of(&self, key: &str, port: &str) -> Option<XY> {
        let (cell, pin) = key.split_once('.')?;
        self.choices(cell, pin)
            .iter()
            .find(|(p, _, _)| p == port)
            .map(|c| c.1)
    }

    /// Take up the segments the footprint cuts and those hanging from them; true when some stay.
    pub fn trim(&mut self, net: &str, cells: &[XY]) -> Result<bool, Decline> {
        let Some(wire) = self.wires.get(net).cloned() else {
            return Ok(false);
        };
        let hit: Set<XY> = cells.iter().cloned().collect();
        let segments = &wire.segments;
        let mut gone: Vec<usize> = (0..segments.len())
            .filter(|i| segments[*i].1.iter().any(|c| hit.contains(c)))
            .collect();
        if gone.is_empty() {
            return Ok(false);
        }
        let before = self.runs_of(net, &wire)?;
        let mut ports: Set<XY> = wire
            .ports
            .iter()
            .filter_map(|(k, p)| self.attach_of(k, p))
            .collect();
        let n = self.rec.nets.get(net).ok_or("an unknown net")?;
        for id in n.sources.iter().chain(&n.sinks) {
            let pin = self.rec.pins.get(id).ok_or("an unknown pin")?;
            if self.placed(&pin.cell) && pin.bound {
                ports.extend(self.choices(&pin.cell, &pin.pin).iter().map(|c| c.1));
            }
        }
        let head = |i: usize| segments[i].1[0];
        let tail = |i: usize| segments[i].1[segments[i].1.len() - 1];
        let hangs_at = |i: usize, end: XY| -> bool {
            if segments[..i].iter().any(|o| o.1.contains(&end)) {
                return true;
            }
            !ports.contains(&end)
                && segments
                    .iter()
                    .enumerate()
                    .any(|(j, o)| j != i && o.1.contains(&end))
        };
        let leaves: Vec<bool> = (0..segments.len()).map(|i| hangs_at(i, head(i))).collect();
        let joins: Vec<bool> = (0..segments.len()).map(|i| hangs_at(i, tail(i))).collect();
        let own = |i: usize| -> Set<XY> {
            let mut out: Set<XY> = segments[i].1.iter().cloned().collect();
            if leaves[i] {
                out.remove(&head(i));
            }
            if joins[i] {
                out.remove(&tail(i));
            }
            out
        };
        loop {
            let lost: Set<XY> = gone.iter().flat_map(|i| own(*i)).collect();
            let more: Vec<usize> = (0..segments.len())
                .filter(|i| {
                    !gone.contains(i)
                        && ((leaves[*i] && lost.contains(&head(*i)))
                            || (joins[*i] && lost.contains(&tail(*i))))
                })
                .collect();
            if more.is_empty() {
                break;
            }
            gone.extend(more);
        }
        let lost: Set<XY> = gone
            .iter()
            .flat_map(|i| segments[*i].1.iter().cloned())
            .collect();
        let kept: Vec<usize> = (0..segments.len()).filter(|i| !gone.contains(i)).collect();
        if kept.is_empty() {
            return Ok(false);
        }
        let staying: Set<XY> = kept
            .iter()
            .flat_map(|i| segments[*i].1.iter().cloned())
            .collect();
        let freed: Set<XY> = lost.difference(&staying).cloned().collect();
        let cut: Set<XY> = gone
            .iter()
            .flat_map(|i| [head(*i), tail(*i)])
            .filter(|c| staying.contains(c))
            .collect();
        let holder = format!("wire:{net}");
        let layers: BTreeSet<String> = gone.iter().map(|i| segments[*i].0.clone()).collect();
        for layer in &layers {
            let mut layer_cells: Vec<XY> = gone
                .iter()
                .filter(|i| &segments[**i].0 == layer)
                .flat_map(|i| segments[*i].1.iter().cloned())
                .filter(|c| freed.contains(c))
                .collect();
            layer_cells.sort();
            if !layer_cells.is_empty() {
                self.free(layer, &layer_cells, &holder);
            }
        }
        let mut units = Vec::new();
        for unit in &wire.units {
            let Some(found) = self.units.get(unit) else {
                continue;
            };
            let at = (found.x, found.y);
            let ends = kept.iter().any(|k| at == head(*k) || at == tail(*k));
            if freed.contains(&at) || (cut.contains(&at) && !ends) {
                self.remove_unit(unit)?;
            } else {
                units.push(unit.clone());
            }
        }
        let ports: Vec<(String, String)> = wire
            .ports
            .iter()
            .filter(|(k, p)| self.attach_of(k, p).is_none_or(|xy| !freed.contains(&xy)))
            .cloned()
            .collect();
        let trimmed =
            Wire { segments: kept.iter().map(|i| segments[*i].clone()).collect(), units, ports };
        self.wires.insert(net.to_string(), trimmed.clone());
        self.retable(net);
        let runs = self.runs_of(net, &trimmed)?;
        self.write_runs(&holder, &runs, &before);
        let mut sorted: Vec<XY> = freed.into_iter().collect();
        sorted.sort();
        let shared: Vec<String> = layers
            .iter()
            .flat_map(|l| self.units_on(l, &sorted))
            .collect();
        self.drop_shared_units(&shared, net)?;
        Ok(true)
    }

    /// Write a newly placed cell's pins into the attach tables, its nets retabled after.
    pub fn table_cell(&mut self, cell: &str) -> Result<(), Decline> {
        let mut touched = Vec::new();
        for net in self.nets_of(cell) {
            let n = self.rec.nets.get(&net).ok_or("an unknown net")?;
            let layer = self.layer_of(&n.carrier)?.to_string();
            for id in n.sources.iter().chain(&n.sinks) {
                let pin = self.rec.pins.get(id).ok_or("an unknown pin")?;
                if pin.cell != cell {
                    continue;
                }
                let entry = (cell.to_string(), pin.pin.clone(), layer.clone());
                self.attach.pins.entry_or_default(net.clone()).push(entry);
            }
            touched.push(net);
        }
        for net in touched {
            self.retable(&net);
        }
        Ok(())
    }

    pub fn nets_of(&self, cell: &str) -> Vec<String> {
        self.rec.cell_nets.get(cell).cloned().unwrap_or_default()
    }

    /// Whether the net can route: a placed source or the outside, and a placed sink.
    pub fn ready(&self, net: &str) -> bool {
        let Some(n) = self.rec.nets.get(net) else {
            return false;
        };
        let placed = |id: &String| self.rec.pins.get(id).is_some_and(|p| self.placed(&p.cell));
        (n.outside || n.sources.iter().any(placed)) && n.sinks.iter().any(placed)
    }

    /// The widest distance between two placed attach cells of the net.
    pub fn span(&self, net: &str) -> i64 {
        let Some(n) = self.rec.nets.get(net) else {
            return 0;
        };
        let cells: Vec<XY> = n
            .sources
            .iter()
            .chain(&n.sinks)
            .filter_map(|id| self.rec.pins.get(id))
            .filter_map(|p| self.choice(&p.cell, &p.pin).map(|c| c.1))
            .collect();
        let mut best = 0;
        for a in &cells {
            for b in &cells {
                best = best.max((a.0 - b.0).abs() + (a.1 - b.1).abs());
            }
        }
        best
    }
}
