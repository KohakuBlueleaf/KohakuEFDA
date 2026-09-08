//! The text form: the pest grammar, the parser, the assembler and the writer, on JSON at the boundary.

pub mod assemble;
pub mod levels;
pub mod moves;
pub mod parser;
pub mod stmt;
pub mod values;
pub mod writer;

use crate::ir::model::{Assessment, Layout, Netlist, Problem};
use crate::{Error, Result};

/// Every level the text holds, as one JSON document; `context` is a problem, a netlist or a levels document.
pub fn parse_to_json(text: &str, context: Option<&str>) -> Result<String> {
    let stmts = parser::parse_statements(text)?;
    let ctx = match context {
        Some(c) => Some(levels::context_from_json(c)?),
        None => None,
    };
    let levels = assemble::assemble(&stmts, ctx.as_ref())?;
    Ok(levels::levels_to_json(&levels))
}

/// Canonical text of a level given as content JSON.
pub fn write_from_json(level_json: &str, context: Option<&str>) -> Result<String> {
    let (level, value) = levels::read(level_json)?;
    Ok(match level.as_str() {
        "problem" => writer::write_problem(&serde_json::from_value::<Problem>(value)?),
        "netlist" => writer::write_netlist(&serde_json::from_value::<Netlist>(value)?),
        "layout" => {
            let layout: Layout = serde_json::from_value(value)?;
            let ctx = match context {
                Some(c) => Some(levels::context_from_json(c)?),
                None => None,
            };
            writer::write_layout(&layout, ctx.as_ref().and_then(|c| c.netlist.as_ref()))
        }
        "assessment" => writer::write_assessment(&serde_json::from_value::<Assessment>(value)?),
        other => return Err(Error::Ir(format!("no text form for a {other}"))),
    })
}
