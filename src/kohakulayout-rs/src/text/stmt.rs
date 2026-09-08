//! Statement records: what one line of the text form says, before assembly into levels.

use serde_json::Value;

use crate::ir::geometry::XY;
use crate::ir::model::Attrs;
use crate::ir::rate::Rate;

pub type Opts = std::collections::BTreeMap<String, Value>;

#[derive(Clone, Debug)]
pub enum RegionExpr {
    All,
    Not(String),
    Rects(Vec<(i64, i64, i64, i64)>),
}

#[derive(Clone, Debug)]
pub enum End {
    Pin(String),
    Cell(XY),
}

#[derive(Clone, Debug)]
pub enum Seg {
    Moves {
        start: End,
        moves: Vec<super::moves::Step>,
        end: End,
    },
    Cells {
        cells: Vec<XY>,
        end: End,
    },
}

#[derive(Clone, Debug)]
pub struct PortRec {
    pub id: String,
    pub direction: String,
    pub carrier: String,
    pub side: String,
    pub offset: i64,
    pub attrs: Attrs,
}

#[derive(Clone, Debug)]
pub enum Stmt {
    Header {
        version: i64,
    },
    Physics {
        id: String,
    },
    Fabric {
        size: (i64, i64),
        opts: Opts,
        attrs: Attrs,
    },
    Region {
        id: String,
        expr: RegionExpr,
        attrs: Attrs,
    },
    Carrier {
        id: String,
        layer: String,
        capacity: Option<Rate>,
        opts: Opts,
        attrs: Attrs,
    },
    Param {
        key: String,
        value: Value,
    },
    Cell {
        id: String,
        reference: String,
        opts: Opts,
        attrs: Attrs,
    },
    Pin {
        cell: String,
        pin: String,
        direction: String,
        carrier: String,
        opts: Opts,
    },
    Net {
        id: String,
        carrier: String,
        rate: Option<Rate>,
        opts: Opts,
        attrs: Attrs,
        sources: Vec<String>,
        sinks: Vec<String>,
    },
    Group {
        id: String,
        opts: Opts,
        attrs: Attrs,
        members: Vec<String>,
    },
    Attrs {
        attrs: Attrs,
    },
    Layout {
        digest: String,
        attrs: Attrs,
    },
    Place {
        cell: String,
        xy: XY,
        rot: i64,
    },
    Instance {
        cell: String,
        xy: XY,
        rot: i64,
    },
    Wire {
        net: String,
        opts: Opts,
        segments: Vec<Seg>,
    },
    Unit {
        id: String,
        footprint: String,
        xy: XY,
        rot: i64,
        opts: Opts,
        attrs: Attrs,
    },
    Reserve {
        tag: String,
        layer: String,
        opts: Opts,
        rects: Vec<(i64, i64, i64, i64)>,
    },
    Assessment {
        digest: String,
    },
    Metric {
        name: String,
        value: Value,
    },
    Finding {
        rule: String,
        severity: String,
        subject: String,
        message: String,
        attrs: Attrs,
    },
    Complete(bool),
    Valid(bool),
    Lib {
        id: String,
        size: (i64, i64),
        opts: Opts,
        attrs: Attrs,
        ports: Vec<PortRec>,
    },
    Module {
        id: String,
        items: Vec<Stmt>,
    },
    ModulePort {
        id: String,
        direction: String,
        carrier: String,
        cell: String,
        pin: String,
    },
    Macro {
        id: String,
        module: String,
        items: Vec<Stmt>,
    },
}
