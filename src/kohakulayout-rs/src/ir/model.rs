//! The levels as serde types. Every field a pydantic model dumps is here with the same default,
//! so `serde_json::to_value` of a level is the dict Python's `model_dump` produces.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

use super::geometry::{Rect, ROTATIONS, XY};
use super::rate::Rate;

pub type Attrs = BTreeMap<String, BTreeMap<String, Value>>;

fn default_ground() -> String {
    "ground".to_string()
}
fn default_rotations() -> Vec<i64> {
    ROTATIONS.to_vec()
}
fn default_layers() -> Vec<String> {
    vec!["ground".to_string()]
}
fn default_schema() -> i64 {
    1
}
fn default_free() -> String {
    "free".to_string()
}
fn zero_rate() -> Rate {
    Rate::int(0)
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Port {
    pub id: String,
    pub side: String,
    pub offset: i64,
    pub direction: String,
    pub carrier: String,
    #[serde(default)]
    pub attrs: Attrs,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Footprint {
    pub id: String,
    pub width: i64,
    pub height: i64,
    #[serde(default = "default_ground")]
    pub layer: String,
    #[serde(default)]
    pub occludes: Vec<String>,
    #[serde(default = "default_rotations")]
    pub rotations: Vec<i64>,
    #[serde(default)]
    pub ports: Vec<Port>,
    #[serde(default)]
    pub attrs: Attrs,
}

impl Footprint {
    pub fn port(&self, id: &str) -> Option<&Port> {
        self.ports.iter().find(|p| p.id == id)
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Pin {
    pub id: String,
    pub direction: String,
    pub carrier: String,
    #[serde(default)]
    pub ports: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Constraint {
    #[serde(default = "default_free")]
    pub kind: String,
    #[serde(default)]
    pub attrs: Attrs,
}

impl Default for Constraint {
    fn default() -> Self {
        Constraint { kind: default_free(), attrs: Attrs::new() }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Cell {
    pub id: String,
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub attrs: Attrs,
    #[serde(default)]
    pub footprint: Option<String>,
    #[serde(default)]
    pub module: Option<String>,
    #[serde(default, rename = "macro")]
    pub macro_: Option<String>,
    #[serde(default)]
    pub pins: Vec<Pin>,
    #[serde(default)]
    pub constraint: Constraint,
    #[serde(default)]
    pub group: Option<String>,
    #[serde(default)]
    pub needs: Vec<String>,
}

impl Cell {
    pub fn is_instance(&self) -> bool {
        self.module.is_some() || self.macro_.is_some()
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct PinRef {
    pub cell: String,
    pub pin: String,
}

impl PinRef {
    pub fn text(&self) -> String {
        format!("{}.{}", self.cell, self.pin)
    }
    pub fn parse(text: &str) -> Option<PinRef> {
        let (cell, pin) = text.split_once('.')?;
        Some(PinRef { cell: cell.to_string(), pin: pin.to_string() })
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Net {
    pub id: String,
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub attrs: Attrs,
    pub carrier: String,
    #[serde(default = "zero_rate")]
    pub rate: Rate,
    #[serde(default)]
    pub sources: Vec<PinRef>,
    #[serde(default)]
    pub sinks: Vec<PinRef>,
    #[serde(default)]
    pub outside: Option<String>,
}

impl Net {
    pub fn pins(&self) -> Vec<PinRef> {
        self.sources
            .iter()
            .chain(self.sinks.iter())
            .cloned()
            .collect()
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Group {
    pub id: String,
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub attrs: Attrs,
    #[serde(default)]
    pub members: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ModulePort {
    pub id: String,
    pub direction: String,
    pub carrier: String,
    pub inner: PinRef,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Module {
    pub id: String,
    #[serde(default)]
    pub ports: Vec<ModulePort>,
    pub body: Box<Netlist>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Macro {
    pub id: String,
    pub module: String,
    pub layout: Layout,
    #[serde(default)]
    pub footprint: Option<Footprint>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Netlist {
    #[serde(default = "default_schema")]
    pub schema_version: i64,
    #[serde(default)]
    pub pack: String,
    #[serde(default)]
    pub library: BTreeMap<String, Footprint>,
    #[serde(default)]
    pub cells: BTreeMap<String, Cell>,
    #[serde(default)]
    pub nets: BTreeMap<String, Net>,
    #[serde(default)]
    pub groups: BTreeMap<String, Group>,
    #[serde(default)]
    pub modules: BTreeMap<String, Module>,
    #[serde(default)]
    pub macros: BTreeMap<String, Macro>,
    #[serde(default)]
    pub attrs: Attrs,
}

impl Default for Netlist {
    fn default() -> Self {
        Netlist {
            schema_version: 1,
            pack: String::new(),
            library: BTreeMap::new(),
            cells: BTreeMap::new(),
            nets: BTreeMap::new(),
            groups: BTreeMap::new(),
            modules: BTreeMap::new(),
            macros: BTreeMap::new(),
            attrs: Attrs::new(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Carrier {
    pub id: String,
    pub layer: String,
    #[serde(default)]
    pub capacity: Option<Rate>,
    #[serde(default)]
    pub attrs: Attrs,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Region {
    pub id: String,
    #[serde(default)]
    pub rects: Vec<Rect>,
    #[serde(default)]
    pub attrs: Attrs,
}

impl Region {
    pub fn cells(&self) -> std::collections::BTreeSet<XY> {
        self.rects.iter().flat_map(|r| r.cells()).collect()
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Fabric {
    pub width: i64,
    pub height: i64,
    #[serde(default = "default_layers")]
    pub layers: Vec<String>,
    #[serde(default)]
    pub carriers: BTreeMap<String, Carrier>,
    #[serde(default)]
    pub regions: BTreeMap<String, Region>,
    #[serde(default)]
    pub entries: Vec<String>,
    #[serde(default)]
    pub attrs: Attrs,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Placement {
    pub cell: String,
    pub x: i64,
    pub y: i64,
    #[serde(default)]
    pub rot: i64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Segment {
    pub carrier: String,
    pub layer: String,
    pub cells: Vec<XY>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Wire {
    pub net: String,
    #[serde(default)]
    pub segments: Vec<Segment>,
    #[serde(default)]
    pub units: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Unit {
    pub id: String,
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub attrs: Attrs,
    pub footprint: String,
    pub x: i64,
    pub y: i64,
    #[serde(default)]
    pub rot: i64,
    #[serde(default)]
    pub owner: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Reservation {
    pub tag: String,
    pub layer: String,
    pub cells: Vec<XY>,
    #[serde(default)]
    pub carrier: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Layout {
    #[serde(default = "default_schema")]
    pub schema_version: i64,
    #[serde(default)]
    pub problem: String,
    #[serde(default)]
    pub placements: BTreeMap<String, Placement>,
    #[serde(default)]
    pub instances: BTreeMap<String, Placement>,
    #[serde(default)]
    pub wires: BTreeMap<String, Wire>,
    #[serde(default)]
    pub units: BTreeMap<String, Unit>,
    #[serde(default)]
    pub reservations: Vec<Reservation>,
    #[serde(default)]
    pub attrs: Attrs,
}

impl Default for Layout {
    fn default() -> Self {
        Layout {
            schema_version: 1,
            problem: String::new(),
            placements: BTreeMap::new(),
            instances: BTreeMap::new(),
            wires: BTreeMap::new(),
            units: BTreeMap::new(),
            reservations: Vec::new(),
            attrs: Attrs::new(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Finding {
    pub rule: String,
    pub severity: String,
    pub subject: String,
    pub message: String,
    #[serde(default)]
    pub attrs: Attrs,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Assessment {
    #[serde(default = "default_schema")]
    pub schema_version: i64,
    #[serde(default)]
    pub layout: String,
    #[serde(default)]
    pub metrics: BTreeMap<String, Value>,
    #[serde(default)]
    pub findings: Vec<Finding>,
    #[serde(default)]
    pub complete: bool,
    #[serde(default)]
    pub valid: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Problem {
    #[serde(default = "default_schema")]
    pub schema_version: i64,
    #[serde(default)]
    pub physics: String,
    pub fabric: Fabric,
    pub netlist: Netlist,
    #[serde(default)]
    pub params: BTreeMap<String, Value>,
}

/// A level document as JSON with its `level` tag, the way Python's `content()` writes it.
pub fn content<T: Serialize>(level: &str, value: &T) -> Value {
    let mut object = serde_json::to_value(value).expect("a level serialises");
    if let Value::Object(map) = &mut object {
        map.insert("level".to_string(), Value::String(level.to_string()));
    }
    object
}
