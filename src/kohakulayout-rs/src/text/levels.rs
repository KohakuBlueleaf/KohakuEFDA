//! Levels across the JSON boundary: content documents in, canonical forms, flat forms and digests out.

use serde_json::Value;

use super::assemble::Levels;
use crate::ir::digest::digest_of;
use crate::ir::json::canonical;
use crate::ir::model::{content, Assessment, Fabric, Layout, Netlist, Problem};
use crate::{Error, Result};

fn level_of(value: &Value) -> Result<String> {
    value
        .get("level")
        .and_then(|l| l.as_str())
        .map(|s| s.to_string())
        .ok_or_else(|| Error::Ir("a level JSON carries a 'level' key".to_string()))
}

pub fn read(text: &str) -> Result<(String, Value)> {
    let value: Value = serde_json::from_str(text)?;
    let level = level_of(&value)?;
    Ok((level, value))
}

/// A context for parsing or writing: a problem, a netlist, or a `Levels` document from `parse_to_json`.
pub fn context_from_json(text: &str) -> Result<Levels> {
    let value: Value = serde_json::from_str(text)?;
    let mut out = Levels { version: 1, ..Levels::default() };
    match value.get("level").and_then(|l| l.as_str()) {
        Some("problem") => {
            let problem: Problem = serde_json::from_value(value)?;
            out.physics = problem.physics;
            out.params = problem.params;
            out.fabric = Some(problem.fabric);
            out.netlist = Some(problem.netlist);
        }
        Some("netlist") => {
            out.netlist = Some(serde_json::from_value(value)?);
        }
        Some(other) => return Err(Error::Ir(format!("a {other} is no context for the text form"))),
        None => {
            out.physics = value
                .get("physics")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            if let Some(Value::Object(params)) = value.get("params") {
                out.params = params.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
            }
            if let Some(fabric) = value.get("fabric").filter(|v| !v.is_null()) {
                out.fabric = Some(serde_json::from_value(fabric.clone())?);
            }
            if let Some(netlist) = value.get("netlist").filter(|v| !v.is_null()) {
                out.netlist = Some(serde_json::from_value(netlist.clone())?);
            }
        }
    }
    Ok(out)
}

pub fn levels_to_json(levels: &Levels) -> String {
    let mut object = serde_json::Map::new();
    object.insert("version".to_string(), Value::Number(levels.version.into()));
    object.insert("physics".to_string(), Value::String(levels.physics.clone()));
    object.insert(
        "params".to_string(),
        Value::Object(
            levels
                .params
                .iter()
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect(),
        ),
    );
    object.insert(
        "fabric".to_string(),
        levels
            .fabric
            .as_ref()
            .map(|f| serde_json::to_value(f).unwrap())
            .unwrap_or(Value::Null),
    );
    object.insert(
        "netlist".to_string(),
        levels
            .netlist
            .as_ref()
            .map(|n| content("netlist", n))
            .unwrap_or(Value::Null),
    );
    object.insert(
        "layout".to_string(),
        levels
            .layout
            .as_ref()
            .map(|l| content("layout", l))
            .unwrap_or(Value::Null),
    );
    object.insert(
        "assessment".to_string(),
        levels
            .assessment
            .as_ref()
            .map(|a| content("assessment", a))
            .unwrap_or(Value::Null),
    );
    object.insert(
        "problem".to_string(),
        levels
            .problem()
            .map(|p| content("problem", &p))
            .unwrap_or(Value::Null),
    );
    canonical(&Value::Object(object))
}

/// The canonical dict a digest is computed on, per level, as Python's `canonical()` builds it.
pub fn canonical_value(level: &str, value: Value) -> Result<Value> {
    Ok(match level {
        "netlist" => {
            let netlist: Netlist = serde_json::from_value(value)?;
            content("netlist", &netlist.flatten())
        }
        "problem" => {
            let problem: Problem = serde_json::from_value(value)?;
            let mut object = serde_json::Map::new();
            object.insert("level".to_string(), Value::String("problem".to_string()));
            object
                .insert("schema_version".to_string(), Value::Number(problem.schema_version.into()));
            object.insert("physics".to_string(), Value::String(problem.physics.clone()));
            object.insert("fabric".to_string(), serde_json::to_value(&problem.fabric)?);
            object.insert("netlist".to_string(), serde_json::to_value(problem.netlist.flatten())?);
            object.insert(
                "params".to_string(),
                Value::Object(
                    problem
                        .params
                        .iter()
                        .map(|(k, v)| (k.clone(), v.clone()))
                        .collect(),
                ),
            );
            Value::Object(object)
        }
        "layout" => {
            let layout: Layout = serde_json::from_value(value)?;
            content("layout", &layout)
        }
        "assessment" => {
            let assessment: Assessment = serde_json::from_value(value)?;
            content("assessment", &assessment)
        }
        other => return Err(Error::Ir(format!("unknown level {other:?}"))),
    })
}

pub fn canonical_json(text: &str) -> Result<String> {
    let (level, value) = read(text)?;
    Ok(canonical(&canonical_value(&level, value)?))
}

pub fn digest_json(text: &str) -> Result<String> {
    let (level, value) = read(text)?;
    Ok(digest_of(&canonical_value(&level, value)?))
}

pub fn flatten_json(text: &str) -> Result<String> {
    let (level, value) = read(text)?;
    Ok(match level.as_str() {
        "netlist" => {
            let netlist: Netlist = serde_json::from_value(value)?;
            canonical(&content("netlist", &netlist.flatten()))
        }
        "problem" => {
            let mut problem: Problem = serde_json::from_value(value)?;
            problem.netlist = problem.netlist.flatten();
            canonical(&content("problem", &problem))
        }
        other => return Err(Error::Ir(format!("{other} does not flatten"))),
    })
}

pub fn fabric_value(fabric: &Fabric) -> Value {
    serde_json::to_value(fabric).unwrap()
}
