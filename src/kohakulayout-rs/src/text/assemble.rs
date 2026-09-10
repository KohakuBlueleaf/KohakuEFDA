//! Statement records to levels: the fabric, the netlist with its scopes, the layout, the assessment.
//! A port of Python's `assemble.py`, resolving references after every definition is seen.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

use super::moves::{cells_from_moves, Step};
use super::stmt::{End, Opts, RegionExpr, Seg, Stmt};
use crate::ir::geometry::{attach_cell, rects_from_cells, Rect, XY};
use crate::ir::hier::derive_footprint;
use crate::ir::model::{
    Assessment, Attrs, Carrier, Cell, Constraint, Fabric, Finding, Footprint, Group, Layout, Macro,
    Module, ModulePort, Net, Netlist, Pin, PinRef, Placement, Port, Problem, Region, Reservation,
    Segment, Unit, Wire,
};
use crate::ir::rate::Rate;
use crate::{Error, Result};

const CELL_OPTS: [&str; 5] = ["kind", "at", "group", "needs", "label"];

#[derive(Clone, Debug, Default)]
pub struct Levels {
    pub version: i64,
    pub physics: String,
    pub params: BTreeMap<String, Value>,
    pub fabric: Option<Fabric>,
    pub netlist: Option<Netlist>,
    pub layout: Option<Layout>,
    pub assessment: Option<Assessment>,
}

impl Levels {
    pub fn problem(&self) -> Option<Problem> {
        Some(Problem {
            schema_version: 1,
            physics: self.physics.clone(),
            fabric: self.fabric.clone()?,
            netlist: self.netlist.clone()?,
            params: self.params.clone(),
        })
    }
}

fn as_list(value: Option<&Value>) -> Vec<Value> {
    match value {
        None => Vec::new(),
        Some(Value::Array(items)) => items.clone(),
        Some(other) => vec![other.clone()],
    }
}

fn as_text(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        Value::Bool(b) => (if *b { "True" } else { "False" }).to_string(),
        other => other.to_string(),
    }
}

fn region_of(id: &str, cells: &BTreeSet<XY>, attrs: Attrs) -> Region {
    Region { id: id.to_string(), rects: rects_from_cells(cells), attrs }
}

fn fabric(stmts: &[Stmt]) -> Result<Option<Fabric>> {
    let Some(Stmt::Fabric { size, opts, attrs }) =
        stmts.iter().find(|s| matches!(s, Stmt::Fabric { .. }))
    else {
        return Ok(None);
    };
    let (width, height) = *size;
    let layers: Vec<String> = match opts.get("layers") {
        None => vec!["ground".to_string()],
        some => as_list(some).iter().map(as_text).collect(),
    };
    let entries: Vec<String> = as_list(opts.get("entries")).iter().map(as_text).collect();
    let mut carriers = BTreeMap::new();
    for s in stmts {
        if let Stmt::Carrier { id, layer, capacity, attrs, .. } = s {
            carriers.insert(
                id.clone(),
                Carrier {
                    id: id.clone(),
                    layer: layer.clone(),
                    capacity: *capacity,
                    attrs: attrs.clone(),
                },
            );
        }
    }
    let every: BTreeSet<XY> = (0..height)
        .flat_map(|y| (0..width).map(move |x| (x, y)))
        .collect();
    let mut regions: BTreeMap<String, Region> = BTreeMap::new();
    for s in stmts {
        if let Stmt::Region { id, expr, attrs } = s {
            match expr {
                RegionExpr::All => {
                    regions.insert(id.clone(), region_of(id, &every, attrs.clone()));
                }
                RegionExpr::Rects(rects) => {
                    let cells: BTreeSet<XY> = rects
                        .iter()
                        .flat_map(|(x, y, w, h)| Rect { x: *x, y: *y, w: *w, h: *h }.cells())
                        .collect();
                    regions.insert(id.clone(), region_of(id, &cells, attrs.clone()));
                }
                RegionExpr::Not(_) => {}
            }
        }
    }
    for s in stmts {
        if let Stmt::Region { id, expr: RegionExpr::Not(other), attrs } = s {
            let Some(base) = regions.get(other) else {
                return Err(Error::Text(format!(
                    "region {id}: 'not {other}' names an undefined region"
                )));
            };
            let cells: BTreeSet<XY> = every.difference(&base.cells()).cloned().collect();
            regions.insert(id.clone(), region_of(id, &cells, attrs.clone()));
        }
    }
    if !regions.contains_key("build") {
        regions.insert("build".to_string(), region_of("build", &every, Attrs::new()));
    }
    Ok(Some(Fabric {
        width,
        height,
        layers,
        carriers,
        regions,
        entries,
        attrs: attrs.clone(),
    }))
}

fn constraint(opts: &Opts, pack: &str) -> Constraint {
    let kind = opts
        .get("at")
        .map(as_text)
        .unwrap_or_else(|| "free".to_string());
    let mut attrs = Attrs::new();
    for (key, value) in opts {
        if CELL_OPTS.contains(&key.as_str()) {
            continue;
        }
        if let Some(rest) = key.strip_prefix("at.") {
            let (ns, name) = rest.split_once('.').unwrap_or((rest, ""));
            attrs
                .entry(ns.to_string())
                .or_default()
                .insert(name.to_string(), value.clone());
        } else {
            let ns = if pack.is_empty() { "pack" } else { pack };
            attrs
                .entry(ns.to_string())
                .or_default()
                .insert(key.clone(), value.clone());
        }
    }
    Constraint { kind, attrs }
}

fn scope(items: &[Stmt], pack: &str, parent: Option<&Netlist>) -> Result<Netlist> {
    let mut library: BTreeMap<String, Footprint> = BTreeMap::new();
    for s in items {
        if let Stmt::Lib { id, size, opts, attrs, ports } = s {
            library.insert(
                id.clone(),
                Footprint {
                    id: id.clone(),
                    width: size.0,
                    height: size.1,
                    layer: opts
                        .get("layer")
                        .map(as_text)
                        .unwrap_or_else(|| "ground".to_string()),
                    occludes: as_list(opts.get("occludes")).iter().map(as_text).collect(),
                    rotations: match opts.get("rot") {
                        None => vec![0, 90, 180, 270],
                        some => as_list(some)
                            .iter()
                            .map(|v| v.as_i64().unwrap_or(0))
                            .collect(),
                    },
                    ports: ports
                        .iter()
                        .map(|p| Port {
                            id: p.id.clone(),
                            side: p.side.clone(),
                            offset: p.offset,
                            direction: p.direction.clone(),
                            carrier: p.carrier.clone(),
                            attrs: p.attrs.clone(),
                        })
                        .collect(),
                    attrs: attrs.clone(),
                },
            );
        }
    }
    let mut seen_library = parent.map(|p| p.library.clone()).unwrap_or_default();
    seen_library.extend(library.clone());
    let mut modules: BTreeMap<String, Module> = BTreeMap::new();
    for s in items {
        if let Stmt::Module { id, items: body } = s {
            let ports: Vec<ModulePort> = body
                .iter()
                .filter_map(|p| match p {
                    Stmt::ModulePort { id, direction, carrier, cell, pin } => Some(ModulePort {
                        id: id.clone(),
                        direction: direction.clone(),
                        carrier: carrier.clone(),
                        inner: PinRef { cell: cell.clone(), pin: pin.clone() },
                    }),
                    _ => None,
                })
                .collect();
            let body_items: Vec<Stmt> = body
                .iter()
                .filter(|p| !matches!(p, Stmt::ModulePort { .. }))
                .cloned()
                .collect();
            let mut scope_modules = parent.map(|p| p.modules.clone()).unwrap_or_default();
            scope_modules.extend(modules.clone());
            let scope_parent = Netlist {
                pack: pack.to_string(),
                library: seen_library.clone(),
                modules: scope_modules,
                ..Netlist::default()
            };
            let inner = scope(&body_items, pack, Some(&scope_parent))?;
            modules.insert(id.clone(), Module { id: id.clone(), ports, body: Box::new(inner) });
        }
    }
    let mut seen_modules = parent.map(|p| p.modules.clone()).unwrap_or_default();
    seen_modules.extend(modules.clone());
    let mut macros: BTreeMap<String, Macro> = BTreeMap::new();
    for s in items {
        if let Stmt::Macro { id, module, items: body } = s {
            let fragment = layout(body, &Levels::default(), true)?;
            macros.insert(
                id.clone(),
                Macro { id: id.clone(), module: module.clone(), layout: fragment, footprint: None },
            );
        }
    }
    let mut seen_macros = parent.map(|p| p.macros.clone()).unwrap_or_default();
    seen_macros.extend(macros.clone());
    let mut cells: BTreeMap<String, Cell> = BTreeMap::new();
    for s in items {
        if let Stmt::Cell { id, reference, opts, attrs } = s {
            let (footprint, module, macro_) = if seen_library.contains_key(reference) {
                (Some(reference.clone()), None, None)
            } else if seen_modules.contains_key(reference) {
                (None, Some(reference.clone()), None)
            } else if seen_macros.contains_key(reference) {
                (None, None, Some(reference.clone()))
            } else {
                return Err(Error::Text(format!(
                    "cell {id}: {reference:?} is not a footprint, module or macro"
                )));
            };
            cells.insert(
                id.clone(),
                Cell {
                    id: id.clone(),
                    kind: opts
                        .get("kind")
                        .map(as_text)
                        .unwrap_or_else(|| reference.clone()),
                    label: opts.get("label").map(as_text).unwrap_or_default(),
                    attrs: attrs.clone(),
                    footprint,
                    module,
                    macro_,
                    pins: Vec::new(),
                    constraint: constraint(opts, pack),
                    group: opts.get("group").map(as_text),
                    needs: as_list(opts.get("needs")).iter().map(as_text).collect(),
                },
            );
        }
    }
    for s in items {
        if let Stmt::Pin { cell, pin, direction, carrier, opts } = s {
            let Some(target) = cells.get_mut(cell) else {
                return Err(Error::Text(format!("pin {cell}.{pin}: no such cell in this scope")));
            };
            let ports_text = opts
                .get("ports")
                .map(as_text)
                .unwrap_or_else(|| pin.clone());
            let ports: Vec<String> = ports_text.split('|').map(|p| p.to_string()).collect();
            target.pins.push(Pin {
                id: pin.clone(),
                direction: direction.clone(),
                carrier: carrier.clone(),
                ports,
            });
        }
    }
    let mut groups: BTreeMap<String, Group> = BTreeMap::new();
    for s in items {
        if let Stmt::Group { id, opts, attrs, members } = s {
            groups.insert(
                id.clone(),
                Group {
                    id: id.clone(),
                    kind: opts.get("kind").map(as_text).unwrap_or_default(),
                    label: String::new(),
                    attrs: attrs.clone(),
                    members: members.clone(),
                },
            );
            for member in members {
                if let Some(cell) = cells.get_mut(member) {
                    cell.group = Some(id.clone());
                }
            }
        }
    }
    let mut nets: BTreeMap<String, Net> = BTreeMap::new();
    for s in items {
        if let Stmt::Net { id, carrier, rate, opts, attrs, sources, sinks } = s {
            let refs = |list: &Vec<String>| {
                list.iter()
                    .filter_map(|r| PinRef::parse(r))
                    .collect::<Vec<_>>()
            };
            nets.insert(
                id.clone(),
                Net {
                    id: id.clone(),
                    kind: opts.get("kind").map(as_text).unwrap_or_default(),
                    label: opts.get("label").map(as_text).unwrap_or_default(),
                    attrs: attrs.clone(),
                    carrier: carrier.clone(),
                    rate: rate.unwrap_or(Rate::int(0)),
                    sources: refs(sources),
                    sinks: refs(sinks),
                    outside: opts.get("outside").map(as_text),
                },
            );
        }
    }
    let mut attrs = Attrs::new();
    for s in items {
        if let Stmt::Attrs { attrs: more } = s {
            for (ns, values) in more {
                attrs.entry(ns.clone()).or_default().extend(values.clone());
            }
        }
    }
    let netlist = Netlist {
        schema_version: 1,
        pack: if parent.is_none() {
            pack.to_string()
        } else {
            String::new()
        },
        library,
        cells,
        nets,
        groups,
        modules,
        macros,
        attrs,
    };
    derive_macros(netlist, parent)
}

fn derive_macros(netlist: Netlist, parent: Option<&Netlist>) -> Result<Netlist> {
    if netlist.macros.is_empty() {
        return Ok(netlist);
    }
    let scope_view = match parent {
        Some(p) => netlist.with_library(p),
        None => netlist.clone(),
    };
    let mut macros = BTreeMap::new();
    for (key, macro_) in &netlist.macros {
        let Some(module) = scope_view.modules.get(&macro_.module) else {
            return Err(Error::Text(format!(
                "macro {key}: module {:?} is not defined",
                macro_.module
            )));
        };
        let body = module.body.with_library(&scope_view).flatten();
        let footprints: BTreeMap<String, Footprint> = body
            .cells
            .keys()
            .filter_map(|k| body.footprint_for(k).map(|fp| (k.clone(), fp.clone())))
            .collect();
        let pins: BTreeMap<String, BTreeMap<String, Vec<String>>> = body
            .cells
            .keys()
            .map(|k| {
                (
                    k.clone(),
                    body.pins_of(k)
                        .into_iter()
                        .map(|p| (p.id, p.ports))
                        .collect(),
                )
            })
            .collect();
        let (derived, problems) = derive_footprint(macro_, module, &footprints, &pins);
        if !problems.is_empty() {
            return Err(Error::Text(problems.join("; ")));
        }
        let mut done = macro_.clone();
        done.footprint = derived;
        macros.insert(key.clone(), done);
    }
    let mut out = netlist;
    out.macros = macros;
    Ok(out)
}

/// The attach cell of a placed pin's first allowed port; Python's `Layout.attach`.
pub fn attach(layout: &Layout, netlist: &Netlist, r: &PinRef, port_id: Option<&str>) -> Option<XY> {
    let placement = layout.placements.get(&r.cell)?;
    let fp = netlist.footprint_for(&r.cell)?;
    let pin = netlist.pin(r)?;
    let chosen = match port_id {
        Some(id) if pin.ports.iter().any(|p| p == id) => id,
        _ => pin.ports.first()?,
    };
    let port = fp.port(chosen)?;
    let (ax, ay) = attach_cell(fp.width, fp.height, &port.side, port.offset, placement.rot);
    Some((placement.x + ax, placement.y + ay))
}

fn ports_of(opts: &Opts) -> BTreeMap<String, String> {
    as_list(opts.get("ports"))
        .iter()
        .map(|item| {
            let text = as_text(item);
            let (r, port) = text.split_once(':').unwrap_or((text.as_str(), ""));
            (r.to_string(), port.to_string())
        })
        .collect()
}

fn endpoint(
    item: &End,
    netlist: Option<&Netlist>,
    partial: &Layout,
    ports: &BTreeMap<String, String>,
) -> Result<XY> {
    match item {
        End::Cell(xy) => Ok(*xy),
        End::Pin(text) => {
            let Some(netlist) = netlist else {
                return Err(Error::Text(format!(
                    "wire endpoint {text}: a pin reference needs the netlist in context"
                )));
            };
            let r = PinRef::parse(text)
                .ok_or_else(|| Error::Text(format!("wire endpoint {text}: not a pin reference")))?;
            attach(partial, netlist, &r, ports.get(text).map(String::as_str)).ok_or_else(|| {
                Error::Text(format!(
                    "wire endpoint {text}: the cell is not placed or the pin is unknown"
                ))
            })
        }
    }
}

fn layout(stmts: &[Stmt], context: &Levels, _relative: bool) -> Result<Layout> {
    let flat = context.netlist.as_ref().map(|n| n.flatten());
    let netlist = flat.as_ref();
    let fabric = context.fabric.as_ref();
    let head = stmts.iter().find_map(|s| match s {
        Stmt::Layout { digest, attrs } => Some((digest.clone(), attrs.clone())),
        _ => None,
    });
    let mut placements = BTreeMap::new();
    let mut instances = BTreeMap::new();
    for s in stmts {
        match s {
            Stmt::Place { cell, xy, rot } => {
                placements.insert(
                    cell.clone(),
                    Placement { cell: cell.clone(), x: xy.0, y: xy.1, rot: *rot },
                );
            }
            Stmt::Instance { cell, xy, rot } => {
                instances.insert(
                    cell.clone(),
                    Placement { cell: cell.clone(), x: xy.0, y: xy.1, rot: *rot },
                );
            }
            _ => {}
        }
    }
    let partial = Layout {
        placements: placements.clone(),
        instances: instances.clone(),
        ..Layout::default()
    };
    let mut wires = BTreeMap::new();
    for s in stmts {
        let Stmt::Wire { net, opts, segments } = s else {
            continue;
        };
        let net_model = netlist.and_then(|n| n.nets.get(net));
        let carrier = opts
            .get("carrier")
            .map(as_text)
            .unwrap_or_else(|| net_model.map(|n| n.carrier.clone()).unwrap_or_default());
        let layer = opts.get("layer").map(as_text).unwrap_or_else(|| {
            fabric
                .and_then(|f| f.carriers.get(&carrier))
                .map(|c| c.layer.clone())
                .unwrap_or_default()
        });
        if carrier.is_empty() || layer.is_empty() {
            return Err(Error::Text(format!("wire {net}: carrier and layer are unknown; give carrier= and layer= or the problem")));
        }
        let mut out_segments = Vec::new();
        let ports = ports_of(opts);
        for seg in segments {
            let cells = match seg {
                Seg::Cells { cells, end } => {
                    let end = endpoint(end, netlist, &partial, &ports)?;
                    let mut cells = cells.clone();
                    if *cells.last().unwrap() != end {
                        cells.push(end);
                    }
                    cells
                }
                Seg::Moves { start, moves, end } => {
                    let end = endpoint(end, netlist, &partial, &ports)?;
                    let start = endpoint(start, netlist, &partial, &ports)?;
                    let steps: Vec<Step> = moves.clone();
                    let cells = cells_from_moves(start, &steps).map_err(Error::Text)?;
                    if *cells.last().unwrap() != end {
                        return Err(Error::Text(format!(
                            "wire {net}: the path ends at ({}, {}), not at ({}, {})",
                            cells.last().unwrap().0,
                            cells.last().unwrap().1,
                            end.0,
                            end.1
                        )));
                    }
                    cells
                }
            };
            out_segments.push(Segment { carrier: carrier.clone(), layer: layer.clone(), cells });
        }
        wires.insert(
            net.clone(),
            Wire {
                net: net.clone(),
                segments: out_segments,
                units: as_list(opts.get("units")).iter().map(as_text).collect(),
                ports,
            },
        );
    }
    let mut units = BTreeMap::new();
    for s in stmts {
        if let Stmt::Unit { id, footprint, xy, rot, opts, attrs } = s {
            units.insert(
                id.clone(),
                Unit {
                    id: id.clone(),
                    kind: opts
                        .get("kind")
                        .map(as_text)
                        .unwrap_or_else(|| footprint.clone()),
                    label: String::new(),
                    attrs: attrs.clone(),
                    footprint: footprint.clone(),
                    x: xy.0,
                    y: xy.1,
                    rot: *rot,
                    owner: opts.get("owner").map(as_text).unwrap_or_default(),
                },
            );
        }
    }
    let mut reservations = Vec::new();
    for s in stmts {
        if let Stmt::Reserve { tag, layer, opts, rects } = s {
            let cells: BTreeSet<XY> = rects
                .iter()
                .flat_map(|(x, y, w, h)| Rect { x: *x, y: *y, w: *w, h: *h }.cells())
                .collect();
            reservations.push(Reservation {
                tag: tag.clone(),
                layer: layer.clone(),
                cells: cells.into_iter().collect(),
                carrier: opts.get("carrier").map(as_text),
            });
        }
    }
    let (problem, attrs) = head.unwrap_or_default();
    Ok(Layout {
        schema_version: 1,
        problem,
        placements,
        instances,
        wires,
        units,
        reservations,
        attrs,
    })
}

fn assessment(stmts: &[Stmt]) -> Option<Assessment> {
    let head = stmts.iter().find_map(|s| match s {
        Stmt::Assessment { digest } => Some(digest.clone()),
        _ => None,
    });
    let metrics: BTreeMap<String, Value> = stmts
        .iter()
        .filter_map(|s| match s {
            Stmt::Metric { name, value } => Some((name.clone(), value.clone())),
            _ => None,
        })
        .collect();
    let findings: Vec<Finding> = stmts
        .iter()
        .filter_map(|s| match s {
            Stmt::Finding { rule, severity, subject, message, attrs } => Some(Finding {
                rule: rule.clone(),
                severity: severity.clone(),
                subject: subject.clone(),
                message: message.clone(),
                attrs: attrs.clone(),
            }),
            _ => None,
        })
        .collect();
    if head.is_none() && metrics.is_empty() && findings.is_empty() {
        return None;
    }
    let complete = stmts
        .iter()
        .find_map(|s| {
            if let Stmt::Complete(v) = s {
                Some(*v)
            } else {
                None
            }
        })
        .unwrap_or(false);
    let valid = stmts
        .iter()
        .find_map(|s| {
            if let Stmt::Valid(v) = s {
                Some(*v)
            } else {
                None
            }
        })
        .unwrap_or(false);
    Some(Assessment {
        schema_version: 1,
        layout: head.unwrap_or_default(),
        metrics,
        findings,
        complete,
        valid,
    })
}

fn is_netlist(s: &Stmt) -> bool {
    matches!(
        s,
        Stmt::Lib { .. }
            | Stmt::Cell { .. }
            | Stmt::Pin { .. }
            | Stmt::Net { .. }
            | Stmt::Group { .. }
            | Stmt::Module { .. }
            | Stmt::Macro { .. }
            | Stmt::Attrs { .. }
    )
}

fn is_layout(s: &Stmt) -> bool {
    matches!(
        s,
        Stmt::Layout { .. }
            | Stmt::Place { .. }
            | Stmt::Instance { .. }
            | Stmt::Wire { .. }
            | Stmt::Unit { .. }
            | Stmt::Reserve { .. }
    )
}

fn is_assessment(s: &Stmt) -> bool {
    matches!(
        s,
        Stmt::Assessment { .. }
            | Stmt::Metric { .. }
            | Stmt::Finding { .. }
            | Stmt::Complete(_)
            | Stmt::Valid(_)
    )
}

pub fn assemble(stmts: &[Stmt], context: Option<&Levels>) -> Result<Levels> {
    let mut out = Levels { version: 1, ..Levels::default() };
    if let Some(Stmt::Header { version }) = stmts.iter().find(|s| matches!(s, Stmt::Header { .. }))
    {
        out.version = *version;
    }
    out.physics = stmts
        .iter()
        .find_map(|s| {
            if let Stmt::Physics { id } = s {
                Some(id.clone())
            } else {
                None
            }
        })
        .unwrap_or_else(|| context.map(|c| c.physics.clone()).unwrap_or_default());
    out.params = stmts
        .iter()
        .filter_map(|s| {
            if let Stmt::Param { key, value } = s {
                Some((key.clone(), value.clone()))
            } else {
                None
            }
        })
        .collect();
    out.fabric = match fabric(stmts)? {
        Some(f) => Some(f),
        None => context.and_then(|c| c.fabric.clone()),
    };
    let pack = out.physics.split('@').next().unwrap_or("").to_string();
    let netlist_items: Vec<Stmt> = stmts.iter().filter(|s| is_netlist(s)).cloned().collect();
    if !netlist_items.is_empty() {
        out.netlist = Some(scope(&netlist_items, &pack, None)?);
    } else if let Some(c) = context {
        out.netlist = c.netlist.clone();
    }
    let layout_items: Vec<Stmt> = stmts.iter().filter(|s| is_layout(s)).cloned().collect();
    if !layout_items.is_empty() {
        out.layout = Some(layout(&layout_items, &out, false)?);
    }
    let assess_items: Vec<Stmt> = stmts.iter().filter(|s| is_assessment(s)).cloned().collect();
    out.assessment = assessment(&assess_items);
    Ok(out)
}
