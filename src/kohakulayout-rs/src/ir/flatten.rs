//! Every instance expanded, ids joined with `/`, port nets merged, definitions dropped; Python's `Netlist.flatten`.

use std::collections::{BTreeMap, BTreeSet};

use super::model::{Net, Netlist, PinRef};

fn union(first: &[PinRef], second: &[PinRef]) -> Vec<PinRef> {
    let seen: BTreeSet<String> = first.iter().map(PinRef::text).collect();
    let mut out = first.to_vec();
    out.extend(second.iter().filter(|r| !seen.contains(&r.text())).cloned());
    out
}

impl Netlist {
    pub fn flatten(&self) -> Netlist {
        if self.is_flat() {
            let mut out = self.clone();
            out.modules.clear();
            out.macros.clear();
            return out;
        }
        let mut cells = self.cells.clone();
        let mut nets: Vec<(String, Net)> = self
            .nets
            .iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        let mut groups = self.groups.clone();
        for (key, cell) in self.cells.iter() {
            if !cell.is_instance() {
                continue;
            }
            let module_id = cell
                .module
                .clone()
                .unwrap_or_else(|| self.macros[cell.macro_.as_ref().unwrap()].module.clone());
            let module = &self.modules[&module_id];
            let body = module.body.with_library(self).flatten();
            let prefix = format!("{key}/");
            cells.remove(key);
            for (leaf_key, leaf) in body.cells.iter() {
                let mut moved = leaf.clone();
                moved.id = format!("{prefix}{leaf_key}");
                moved.group = leaf.group.as_ref().map(|g| format!("{prefix}{g}"));
                cells.insert(moved.id.clone(), moved);
            }
            for (group_key, group) in body.groups.iter() {
                let mut moved = group.clone();
                moved.id = format!("{prefix}{group_key}");
                moved.members = group
                    .members
                    .iter()
                    .map(|m| format!("{prefix}{m}"))
                    .collect();
                groups.insert(moved.id.clone(), moved);
            }
            let mut inner_nets: Vec<(String, Net)> = body
                .nets
                .iter()
                .map(|(net_key, net)| {
                    let mut moved = net.clone();
                    moved.id = format!("{prefix}{net_key}");
                    moved.sources = net
                        .sources
                        .iter()
                        .map(|r| PinRef { cell: format!("{prefix}{}", r.cell), pin: r.pin.clone() })
                        .collect();
                    moved.sinks = net
                        .sinks
                        .iter()
                        .map(|r| PinRef { cell: format!("{prefix}{}", r.cell), pin: r.pin.clone() })
                        .collect();
                    (moved.id.clone(), moved)
                })
                .collect();
            let portmap: BTreeMap<String, PinRef> = module
                .ports
                .iter()
                .map(|p| {
                    (
                        p.id.clone(),
                        PinRef {
                            cell: format!("{prefix}{}", p.inner.cell),
                            pin: p.inner.pin.clone(),
                        },
                    )
                })
                .collect();
            for (_, net) in nets.iter_mut() {
                let sources: Vec<PinRef> = net
                    .sources
                    .iter()
                    .map(|r| {
                        if r.cell == *key {
                            portmap.get(&r.pin).cloned().unwrap_or_else(|| r.clone())
                        } else {
                            r.clone()
                        }
                    })
                    .collect();
                let sinks: Vec<PinRef> = net
                    .sinks
                    .iter()
                    .map(|r| {
                        if r.cell == *key {
                            portmap.get(&r.pin).cloned().unwrap_or_else(|| r.clone())
                        } else {
                            r.clone()
                        }
                    })
                    .collect();
                if sources == net.sources && sinks == net.sinks {
                    continue;
                }
                net.sources = sources;
                net.sinks = sinks;
                let mut kept: Vec<(String, Net)> = Vec::new();
                for (inner_key, inner) in inner_nets.drain(..) {
                    let mine: BTreeSet<String> = net.pins().iter().map(PinRef::text).collect();
                    let shared = inner.pins().iter().any(|r| mine.contains(&r.text()));
                    if shared {
                        net.sources = union(&net.sources, &inner.sources);
                        net.sinks = union(&net.sinks, &inner.sinks);
                    } else {
                        kept.push((inner_key, inner));
                    }
                }
                inner_nets = kept;
            }
            nets.extend(inner_nets);
        }
        Netlist {
            schema_version: self.schema_version,
            pack: self.pack.clone(),
            library: self.library.clone(),
            cells,
            nets: nets.into_iter().collect(),
            groups,
            modules: BTreeMap::new(),
            macros: BTreeMap::new(),
            attrs: self.attrs.clone(),
        }
    }
}
