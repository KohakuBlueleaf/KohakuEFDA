//! Levels to canonical text: sorted ids, fixed option order, moves for wires when the netlist is known.
//! A port of Python's `writer.py`, byte for byte.

use std::collections::BTreeMap;

use serde_json::Value;

use super::assemble::attach;
use super::moves::moves_from_cells;
use super::values::{quote, write_loose_value, write_metric, write_value};
use crate::ir::geometry::{rects_from_cells, XY};
use crate::ir::model::{
    Assessment, Attrs, Cell, Fabric, Layout, Macro, Module, Net, Netlist, Pin, PinRef, Problem,
    Region, Wire,
};
use crate::ir::rate::Rate;

const INDENT: &str = "    ";

fn opt(key: &str, value: &Value) -> String {
    format!("{key}={}", write_value(value))
}

fn opt_str(key: &str, value: &str) -> String {
    opt(key, &Value::String(value.to_string()))
}

fn opt_list(key: &str, values: &[String]) -> String {
    opt(key, &Value::Array(values.iter().map(|v| Value::String(v.clone())).collect()))
}

fn attrs(attrs: &Attrs) -> Vec<String> {
    let mut out = Vec::new();
    for (ns, values) in attrs {
        for (key, value) in values {
            out.push(format!("+{ns}.{key}={}", write_loose_value(value)));
        }
    }
    out
}

fn rate(value: &Rate) -> String {
    value.text()
}

// ------------------------------------------------------------------ fabric

fn region_line(region: &Region, fabric: &Fabric) -> String {
    let every = (fabric.width * fabric.height) as usize;
    let body = if region.cells().len() == every {
        "all".to_string()
    } else {
        region
            .rects
            .iter()
            .map(|r| format!("rect {},{} {}x{}", r.x, r.y, r.w, r.h))
            .collect::<Vec<_>>()
            .join(" ")
    };
    let mut parts = vec!["region".to_string(), region.id.clone(), body];
    parts.extend(attrs(&region.attrs));
    parts.join(" ")
}

pub fn fabric_lines(fabric: &Fabric) -> Vec<String> {
    let mut parts = vec![
        "fabric".to_string(),
        format!("{}x{}", fabric.width, fabric.height),
        opt_list("layers", &fabric.layers),
    ];
    if !fabric.entries.is_empty() {
        parts.push(opt_list("entries", &fabric.entries));
    }
    parts.extend(attrs(&fabric.attrs));
    let mut lines = vec![parts.join(" ")];
    for region in fabric.regions.values() {
        lines.push(region_line(region, fabric));
    }
    for carrier in fabric.carriers.values() {
        let mut parts = vec![
            "carrier".to_string(),
            carrier.id.clone(),
            carrier.layer.clone(),
        ];
        if let Some(capacity) = &carrier.capacity {
            parts.push(rate(capacity));
        }
        parts.extend(attrs(&carrier.attrs));
        lines.push(parts.join(" "));
    }
    lines
}

// ----------------------------------------------------------------- netlist

fn lib_lines(netlist: &Netlist, indent: &str) -> Vec<String> {
    let mut lines = Vec::new();
    for fp in netlist.library.values() {
        let mut parts = vec![
            "lib".to_string(),
            fp.id.clone(),
            format!("{}x{}", fp.width, fp.height),
        ];
        if fp.layer != "ground" {
            parts.push(opt_str("layer", &fp.layer));
        }
        if !fp.occludes.is_empty() {
            parts.push(opt_list("occludes", &fp.occludes));
        }
        if fp.rotations != [0, 90, 180, 270] {
            parts.push(opt(
                "rot",
                &Value::Array(
                    fp.rotations
                        .iter()
                        .map(|r| Value::Number((*r).into()))
                        .collect(),
                ),
            ));
        }
        parts.extend(attrs(&fp.attrs));
        let ports: Vec<String> = fp
            .ports
            .iter()
            .map(|p| {
                let mut line = vec![format!(
                    "{} {} {} {}{}",
                    p.id, p.direction, p.carrier, p.side, p.offset
                )];
                line.extend(attrs(&p.attrs));
                line.join(" ")
            })
            .collect();
        if ports.len() <= 4 {
            if ports.is_empty() {
                lines.push(format!("{indent}{} {{ }}", parts.join(" ")));
            } else {
                lines.push(format!("{indent}{} {{ {} }}", parts.join(" "), ports.join(" ; ")));
            }
        } else {
            lines.push(format!("{indent}{} {{", parts.join(" ")));
            for p in ports {
                lines.push(format!("{indent}{INDENT}{p}"));
            }
            lines.push(format!("{indent}}}"));
        }
    }
    lines
}

fn cell_line(cell: &Cell, pack: &str) -> String {
    let reference = cell
        .footprint
        .clone()
        .or_else(|| cell.module.clone())
        .or_else(|| cell.macro_.clone())
        .unwrap_or_default();
    let mut parts = vec!["cell".to_string(), cell.id.clone(), reference.clone()];
    if !cell.kind.is_empty() && cell.kind != reference {
        parts.push(opt_str("kind", &cell.kind));
    }
    if !cell.label.is_empty() {
        parts.push(opt_str("label", &cell.label));
    }
    let constraint = &cell.constraint;
    if constraint.kind != "free" || !constraint.attrs.is_empty() {
        parts.push(opt_str("at", &constraint.kind));
        let own = if pack.is_empty() { "pack" } else { pack };
        for (ns, values) in &constraint.attrs {
            for (key, value) in values {
                let name = if ns == own {
                    key.clone()
                } else {
                    format!("at.{ns}.{key}")
                };
                parts.push(opt(&name, value));
            }
        }
    }
    if let Some(group) = &cell.group {
        parts.push(opt_str("group", group));
    }
    if !cell.needs.is_empty() {
        parts.push(opt_list("needs", &cell.needs));
    }
    parts.extend(attrs(&cell.attrs));
    parts.join(" ")
}

fn default_pins(netlist: &Netlist, cell: &Cell) -> Vec<Pin> {
    let mut view = netlist.clone();
    let mut bare = cell.clone();
    bare.pins.clear();
    view.cells.insert(cell.id.clone(), bare);
    view.pins_of(&cell.id)
}

fn pin_lines(netlist: &Netlist, cell: &Cell) -> Vec<String> {
    if cell.pins.is_empty() || cell.pins == default_pins(netlist, cell) {
        return Vec::new();
    }
    cell.pins
        .iter()
        .map(|p| {
            format!(
                "pin {}.{} {} {} {}",
                cell.id,
                p.id,
                p.direction,
                p.carrier,
                opt_str("ports", &p.ports.join("|"))
            )
        })
        .collect()
}

fn net_line(net: &Net) -> String {
    let mut parts = vec!["net".to_string(), net.id.clone(), net.carrier.clone()];
    if !net.rate.is_zero() {
        parts.push(rate(&net.rate));
    }
    if !net.kind.is_empty() {
        parts.push(opt_str("kind", &net.kind));
    }
    if !net.label.is_empty() {
        parts.push(opt_str("label", &net.label));
    }
    if let Some(outside) = &net.outside {
        parts.push(opt_str("outside", outside));
    }
    parts.extend(attrs(&net.attrs));
    parts.push(":".to_string());
    parts.extend(net.sources.iter().map(PinRef::text));
    parts.push("->".to_string());
    parts.extend(net.sinks.iter().map(PinRef::text));
    parts.join(" ")
}

fn macro_lines(macro_: &Macro, indent: &str) -> Vec<String> {
    let mut lines = vec![format!("{indent}macro {} {} {{", macro_.id, macro_.module)];
    for line in layout_lines(&macro_.layout, None, false) {
        lines.push(format!("{indent}{INDENT}{line}"));
    }
    lines.push(format!("{indent}}}"));
    lines
}

fn module_lines(module: &Module, pack: &str, indent: &str) -> Vec<String> {
    let mut lines = vec![format!("{indent}module {} {{", module.id)];
    for port in &module.ports {
        lines.push(format!(
            "{indent}{INDENT}port {} {} {} = {}",
            port.id,
            port.direction,
            port.carrier,
            port.inner.text()
        ));
    }
    lines.extend(scope_lines(&module.body, pack, &format!("{indent}{INDENT}")));
    lines.push(format!("{indent}}}"));
    lines
}

pub fn scope_lines(netlist: &Netlist, pack: &str, indent: &str) -> Vec<String> {
    let mut lines = Vec::new();
    if !netlist.attrs.is_empty() {
        let mut parts = vec!["attrs".to_string()];
        parts.extend(attrs(&netlist.attrs));
        lines.push(format!("{indent}{}", parts.join(" ")));
    }
    lines.extend(lib_lines(netlist, indent));
    for module in netlist.modules.values() {
        lines.extend(module_lines(module, pack, indent));
    }
    for macro_ in netlist.macros.values() {
        lines.extend(macro_lines(macro_, indent));
    }
    for cell in netlist.cells.values() {
        lines.push(format!("{indent}{}", cell_line(cell, pack)));
        for line in pin_lines(netlist, cell) {
            lines.push(format!("{indent}{line}"));
        }
    }
    for net in netlist.nets.values() {
        lines.push(format!("{indent}{}", net_line(net)));
    }
    for group in netlist.groups.values() {
        let mut parts = vec!["group".to_string(), group.id.clone()];
        if !group.kind.is_empty() {
            parts.push(opt_str("kind", &group.kind));
        }
        parts.extend(attrs(&group.attrs));
        parts.push(":".to_string());
        parts.extend(group.members.iter().cloned());
        lines.push(format!("{indent}{}", parts.join(" ")));
    }
    lines
}

// ------------------------------------------------------------------ layout

fn endpoint(cell_xy: XY, pins: &BTreeMap<XY, PinRef>) -> String {
    match pins.get(&cell_xy) {
        Some(r) => r.text(),
        None => format!("@{},{}", cell_xy.0, cell_xy.1),
    }
}

fn wire_line(wire: &Wire, layout: &Layout, netlist: Option<&Netlist>) -> String {
    let net = netlist.and_then(|n| n.nets.get(&wire.net));
    let mut parts = vec!["wire".to_string(), wire.net.clone()];
    let mut pins: BTreeMap<XY, PinRef> = BTreeMap::new();
    match (net, netlist) {
        (Some(net), Some(netlist)) => {
            for r in net.sources.iter().chain(net.sinks.iter()) {
                if let Some(xy) = attach(layout, netlist, r) {
                    pins.entry(xy).or_insert_with(|| r.clone());
                }
            }
        }
        _ => {
            if let Some(first) = wire.segments.first() {
                parts.push(opt_str("carrier", &first.carrier));
                parts.push(opt_str("layer", &first.layer));
            }
        }
    }
    if !wire.units.is_empty() {
        parts.push(opt_list("units", &wire.units));
    }
    let mut segments = Vec::new();
    for segment in &wire.segments {
        let cells = &segment.cells;
        if net.is_none() || netlist.is_none() {
            let body = if cells.len() > 1 {
                format!(
                    "cells {}",
                    cells[..cells.len() - 1]
                        .iter()
                        .map(|(x, y)| format!("{x},{y}"))
                        .collect::<Vec<_>>()
                        .join(" ")
                )
            } else {
                format!("cells {},{}", cells[0].0, cells[0].1)
            };
            let last = cells.last().unwrap();
            segments.push(format!("{body} -> @{},{}", last.0, last.1));
        } else {
            let mut line = vec![endpoint(cells[0], &pins)];
            line.extend(moves_from_cells(cells));
            line.push("->".to_string());
            line.push(endpoint(*cells.last().unwrap(), &pins));
            segments.push(line.join(" "));
        }
    }
    parts.push(":".to_string());
    parts.push(segments.join(" ; "));
    parts.join(" ")
}

pub fn layout_lines(layout: &Layout, netlist: Option<&Netlist>, header: bool) -> Vec<String> {
    let flat = netlist.map(|n| n.flatten());
    let mut lines = Vec::new();
    if header {
        let mut head = vec!["layout".to_string()];
        if !layout.problem.is_empty() {
            head.push(layout.problem.clone());
        }
        head.extend(attrs(&layout.attrs));
        lines.push(head.join(" "));
    }
    for p in layout.placements.values() {
        lines.push(format!("place {} {},{} r{}", p.cell, p.x, p.y, p.rot));
    }
    for p in layout.instances.values() {
        lines.push(format!("instance {} {},{} r{}", p.cell, p.x, p.y, p.rot));
    }
    for wire in layout.wires.values() {
        lines.push(wire_line(wire, layout, flat.as_ref()));
    }
    for unit in layout.units.values() {
        let mut parts = vec![
            "unit".to_string(),
            unit.id.clone(),
            unit.footprint.clone(),
            format!("{},{}", unit.x, unit.y),
            format!("r{}", unit.rot),
            opt_str("owner", &unit.owner),
        ];
        if !unit.kind.is_empty() && unit.kind != unit.footprint {
            parts.push(opt_str("kind", &unit.kind));
        }
        parts.extend(attrs(&unit.attrs));
        lines.push(parts.join(" "));
    }
    for reservation in &layout.reservations {
        let mut parts = vec![
            "reserve".to_string(),
            reservation.tag.clone(),
            reservation.layer.clone(),
        ];
        if let Some(carrier) = &reservation.carrier {
            if !carrier.is_empty() {
                parts.push(opt_str("carrier", carrier));
            }
        }
        let cells: std::collections::BTreeSet<XY> = reservation.cells.iter().cloned().collect();
        parts.push(":".to_string());
        parts.extend(
            rects_from_cells(&cells)
                .iter()
                .map(|r| format!("rect {},{} {}x{}", r.x, r.y, r.w, r.h)),
        );
        lines.push(parts.join(" "));
    }
    lines
}

// -------------------------------------------------------------- assessment

pub fn assessment_lines(assessment: &Assessment) -> Vec<String> {
    let mut lines = vec![format!("assessment {}", assessment.layout)
        .trim_end()
        .to_string()];
    for (name, value) in &assessment.metrics {
        lines.push(format!("metric {name} {}", write_metric(value)));
    }
    for finding in &assessment.findings {
        let mut parts = vec![
            "finding".to_string(),
            finding.rule.clone(),
            finding.severity.clone(),
            finding.subject.clone(),
            quote(&finding.message),
        ];
        parts.extend(attrs(&finding.attrs));
        lines.push(parts.join(" "));
    }
    lines.push(format!("complete {}", if assessment.complete { "true" } else { "false" }));
    lines.push(format!("valid {}", if assessment.valid { "true" } else { "false" }));
    lines
}

// ----------------------------------------------------------------- entry

pub fn write_problem(problem: &Problem) -> String {
    let mut lines = vec!["kl 1".to_string()];
    if !problem.physics.is_empty() {
        lines.push(format!("physics {}", problem.physics));
    }
    lines.extend(fabric_lines(&problem.fabric));
    for (key, value) in &problem.params {
        lines.push(format!("param {key}={}", write_loose_value(value)));
    }
    let pack = if problem.physics.is_empty() {
        problem.netlist.pack.clone()
    } else {
        problem.physics.split('@').next().unwrap_or("").to_string()
    };
    lines.extend(scope_lines(&problem.netlist, &pack, ""));
    lines.join("\n") + "\n"
}

pub fn write_netlist(netlist: &Netlist) -> String {
    let mut lines = vec!["kl 1".to_string()];
    if !netlist.pack.is_empty() {
        lines.push(format!("physics {}", netlist.pack));
    }
    lines.extend(scope_lines(netlist, &netlist.pack, ""));
    lines.join("\n") + "\n"
}

pub fn write_layout(layout: &Layout, netlist: Option<&Netlist>) -> String {
    let mut lines = vec!["kl 1".to_string()];
    lines.extend(layout_lines(layout, netlist, true));
    lines.join("\n") + "\n"
}

pub fn write_assessment(assessment: &Assessment) -> String {
    let mut lines = vec!["kl 1".to_string()];
    lines.extend(assessment_lines(assessment));
    lines.join("\n") + "\n"
}
