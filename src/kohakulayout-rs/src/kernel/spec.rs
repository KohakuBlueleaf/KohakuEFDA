//! The document one native lay reads: the net's placed pins, its standing wire, its carrier's
//! junction and crossing units, and its tree policy as data.

use serde::Deserialize;

use super::grid::XY;

/// One placed pin: its id, cell, first open attach cell, open ports, whether bound, every port.
#[derive(Clone)]
pub struct Terminal {
    pub id: String,
    pub cell: String,
    pub at: XY,
    pub options: Vec<(String, XY)>,
    pub bound: bool,
    pub choices: Vec<(String, XY, XY)>,
}

/// The net's standing wire as `seed_of` reads it.
#[derive(Default)]
pub struct Seed {
    pub segments: Vec<Vec<XY>>,
    pub junctions: Vec<(XY, String)>,
    pub crossings: Vec<(XY, String, bool)>,
    pub ports: Vec<(String, String)>,
}

/// Where a lane may leave or join its pin's lanes: anywhere, or on long enough straight cells.
#[derive(Deserialize, Clone)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Origins {
    All,
    Straight {
        min_own: usize,
        trunk: Option<(String, String)>,
    },
}

/// The standing lanes a lane with no start or end takes up: none, or those around a tree's trunk.
#[derive(Deserialize, Clone)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Blockers {
    None,
    Trunk { root: String, main: String },
}

/// The lane policy: the lanes in order, the origins, the blockers, whether a join may be one cell.
#[derive(Clone)]
pub struct Policy {
    pub lanes: Vec<(String, String)>,
    pub origins: Origins,
    pub blockers: Blockers,
    pub single_joins: bool,
}

/// The carrier's junction mode (`0` none, `1` free, `2` units) with its split and merge.
pub struct Rules {
    pub junction: u8,
    pub split: Option<String>,
    pub merge: Option<String>,
}

/// One lay: the net, carrier, layer, pins, placed pins, seed, rules, policy and the lane asked for.
pub struct Doc {
    pub net: String,
    pub carrier: String,
    pub layer: String,
    pub sources: Vec<String>,
    pub pins: Vec<String>,
    pub terminals: Vec<Terminal>,
    pub seed: Option<Seed>,
    pub rules: Rules,
    pub policy: Policy,
    pub only: Option<(String, String)>,
}
