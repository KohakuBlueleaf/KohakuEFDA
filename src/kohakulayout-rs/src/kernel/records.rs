//! The world's records mirrored from Python: the statics registered once per world, and the
//! placements, wires, units, attach tables and unit counter synced before each native call.

use serde::Deserialize;

use super::grid::XY;
use super::hash::{Map, Set};
use super::spec::{Blockers, Origins};

/// One net: its carrier, its source and sink pins, whether it reaches the outside.
#[derive(Deserialize, Clone)]
pub struct Net {
    pub id: String,
    pub carrier: String,
    pub sources: Vec<String>,
    pub sinks: Vec<String>,
    pub outside: bool,
}

/// One pin: its id (`cell.pin`), cell, pin name, net, and whether it has one port.
#[derive(Deserialize, Clone)]
pub struct Pin {
    pub id: String,
    pub cell: String,
    pub pin: String,
    pub net: String,
    pub bound: bool,
}

#[derive(Deserialize, Clone)]
pub struct Footprint {
    pub id: String,
    pub width: i64,
    pub height: i64,
    pub layer: String,
    pub occludes: Vec<String>,
    #[serde(default)]
    pub rotations: Vec<i64>,
}

/// A pipe tree's trunk ends and each pin's rate, for the net order's roles.
#[derive(Deserialize, Clone)]
pub struct Tree {
    pub root: String,
    pub main: String,
    pub rates: Map<String, (i64, i64)>,
}

/// How the router orders a placement's nets: by the widest span, or by each net's lane data.
#[derive(Deserialize, Clone)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum NetOrder {
    Span,
    Lanes {
        key: Vec<(i64, i64)>,
        lanes: Vec<(String, String, (i64, i64))>,
        rate: (i64, i64),
        tree: Option<Tree>,
    },
}

/// A carrier's layer, junction mode (`0` none, `1` free, `2` units), run limit and repeater.
#[derive(Deserialize, Clone)]
pub struct Carrier {
    pub id: String,
    pub layer: String,
    pub junction: u8,
    pub split: Option<String>,
    pub merge: Option<String>,
    pub run_limit: Option<i64>,
    pub repeater: Option<String>,
}

/// One swept kind's square sweep: its emitter footprint, size, reach and standing area.
#[derive(Deserialize, Clone)]
pub struct Sweep {
    pub kind: String,
    pub footprint: String,
    pub size: i64,
    pub reach: i64,
    pub area: (i64, i64, i64, i64),
}

/// One emitter: its kind, footprint, reach offsets and whether touching a need covers it.
#[derive(Deserialize, Clone)]
pub struct Emitter {
    pub kind: String,
    pub footprint: String,
    pub offsets: Vec<XY>,
    pub partial: bool,
}

/// The fields as data: every emitter swept by a square sweep.
#[derive(Deserialize, Clone, Default)]
pub struct Fields {
    pub sweeps: Vec<Sweep>,
    pub emitters: Vec<Emitter>,
}

/// A key of fractions, compared as Python compares tuples of numbers.
pub type Key = Vec<(i64, i64)>;
/// A table write: kind, layer, cell, and the value, None when taken out.
pub type CellWrite = (String, String, XY, Option<Value>);
/// A net's attach-table entry: kind, layer, cell.
pub type Entry = (String, String, XY);
/// A net's placed pin in the attach tables: cell, pin, layer.
pub type PinEntry = (String, String, String);

/// One net's lane policy as data: its lanes with their keys, rank key, origins and blockers.
#[derive(Deserialize, Clone)]
pub struct NetPolicy {
    pub order: Vec<(String, String, Key)>,
    pub span: bool,
    pub net_key: Key,
    pub origins: Origins,
    pub blockers: Blockers,
    pub single_joins: bool,
}

/// What a world registers once.
#[derive(Deserialize, Default)]
pub struct Statics {
    pub nets: Vec<Net>,
    pub pins: Vec<Pin>,
    pub footprints: Vec<Footprint>,
    pub share: Vec<(String, String, bool)>,
    pub carriers: Vec<Carrier>,
    pub fields: Option<Fields>,
    pub needs: Vec<(String, Vec<String>)>,
    pub policies: Vec<(String, NetPolicy)>,
    #[serde(default)]
    pub build: Option<Vec<XY>>,
    #[serde(default)]
    pub cell_nets: Vec<(String, Vec<String>)>,
    #[serde(default)]
    pub cell_pins: Vec<(String, Vec<(String, String)>)>,
    #[serde(default)]
    pub transfers: Vec<(String, String)>,
    #[serde(default)]
    pub orders: Vec<(String, NetOrder)>,
}

/// A wire: its segments by layer, the units it placed, the ports it records.
#[derive(Deserialize, Clone, Default)]
pub struct Wire {
    pub segments: Vec<(String, Vec<XY>)>,
    pub units: Vec<String>,
    pub ports: Vec<(String, String)>,
}

#[derive(Deserialize, Clone)]
pub struct Unit {
    pub kind: String,
    pub footprint: String,
    pub x: i64,
    pub y: i64,
    pub rot: i64,
    pub owner: String,
}

/// A placed cell's ports per pin, in the netlist's pin order: port, attach cell, port cell.
pub type Choices = Vec<(String, Vec<(String, XY, XY)>)>;

/// A placed cell: its anchor and footprint, its ports per pin.
#[derive(Deserialize, Clone)]
pub struct Placed {
    pub x: i64,
    pub y: i64,
    pub rot: i64,
    pub footprint: String,
    pub choices: Choices,
}

/// A table cell's value: the net owning it, or the port cell behind it.
#[derive(Deserialize, Clone)]
#[serde(untagged)]
pub enum Value {
    Net(String),
    Cell(XY),
}

/// The attach tables as Python keeps them: open, routed and port cells, per-net entries and pins.
#[derive(Clone, Default)]
pub struct Attach {
    pub open: Map<(String, XY), String>,
    pub routed: Map<(String, XY), String>,
    pub ports: Map<(String, XY), XY>,
    pub entries: Map<String, Vec<(String, String, XY)>>,
    pub pins: Map<String, Vec<(String, String, String)>>,
}

/// One sync: the records changed since the last, or every record.
#[derive(Deserialize, Default)]
pub struct Sync {
    pub full: bool,
    pub placements: Vec<(String, Option<Placed>)>,
    pub order: Option<Vec<String>>,
    pub wires: Vec<(String, Option<Wire>)>,
    pub units: Vec<(String, Option<Unit>)>,
    pub tables_full: bool,
    pub cells: Vec<CellWrite>,
    pub entries: Vec<(String, Vec<Entry>)>,
    pub table_pins: Vec<(String, Vec<PinEntry>)>,
    pub share: Vec<(String, String, bool)>,
    pub unit_seq: u64,
}

/// The mirror: what was registered and what the last sync left.
#[derive(Default)]
pub struct Records {
    pub nets: Map<String, Net>,
    pub pins: Map<String, Pin>,
    /// Per cell, per pin name, the pin's id: the lookup the hot paths make without building a key.
    pub pin_ids: Map<String, Map<String, String>>,
    pub footprints: Map<String, Footprint>,
    pub share: Map<(String, String), bool>,
    pub carriers: Map<String, Carrier>,
    pub placed: Map<String, Placed>,
    pub order: Vec<String>,
    pub fields: Option<Fields>,
    pub needs: Map<String, Vec<String>>,
    pub policies: Map<String, NetPolicy>,
    pub build: Option<Set<XY>>,
    pub cell_nets: Map<String, Vec<String>>,
    pub cell_pins: Map<String, Vec<(String, String)>>,
    pub transfers: Set<(String, String)>,
    pub orders: Map<String, NetOrder>,
    pub wires: Map<String, Wire>,
    pub units: Map<String, Unit>,
    pub attach: Attach,
    pub unit_seq: u64,
    pub ready: bool,
    /// Per layer and attach cell, the placed pins whose port choices may attach there.
    pub alternatives: Map<String, Map<XY, Vec<(String, String)>>>,
    /// Per layer, the open attach cells with their nets, in the cells' order.
    pub open_by_layer: Map<String, Vec<(XY, String)>>,
}

impl Records {
    /// Register a world's fixed records, dropping everything synced before.
    pub fn register(&mut self, statics: Statics) {
        *self = Records::default();
        for net in statics.nets {
            self.nets.insert(net.id.clone(), net);
        }
        for pin in statics.pins {
            self.pin_ids
                .entry(pin.cell.clone())
                .or_default()
                .insert(pin.pin.clone(), pin.id.clone());
            self.pins.insert(pin.id.clone(), pin);
        }
        for fp in statics.footprints {
            self.footprints.insert(fp.id.clone(), fp);
        }
        for carrier in statics.carriers {
            self.carriers.insert(carrier.id.clone(), carrier);
        }
        self.add_share(statics.share);
        self.fields = statics.fields;
        self.needs = statics.needs.into_iter().collect();
        self.policies = statics.policies.into_iter().collect();
        self.build = statics.build.map(|cells| cells.into_iter().collect());
        self.cell_nets = statics.cell_nets.into_iter().collect();
        self.cell_pins = statics.cell_pins.into_iter().collect();
        self.transfers = statics.transfers.into_iter().collect();
        self.orders = statics.orders.into_iter().collect();
        self.ready = true;
    }

    fn add_share(&mut self, rows: Vec<(String, String, bool)>) {
        for (a, b, ok) in rows {
            self.share.insert((b.clone(), a.clone()), ok);
            self.share.insert((a, b), ok);
        }
    }

    /// The id of a cell's pin, or None for a pin no net carries.
    pub fn pin_id(&self, cell: &str, pin: &str) -> Option<&String> {
        self.pin_ids.get(cell)?.get(pin)
    }

    /// Apply one sync.
    pub fn sync(&mut self, sync: Sync) {
        let placements = sync.full || !sync.placements.is_empty();
        let tables = sync.tables_full || !sync.cells.is_empty();
        if let Some(order) = sync.order {
            self.order = order;
        }
        if sync.full {
            self.placed.clear();
            self.wires.clear();
            self.units.clear();
        }
        for (cell, choices) in sync.placements {
            match choices {
                Some(c) => self.placed.insert(cell, c),
                None => self.placed.remove(&cell),
            };
        }
        for (net, wire) in sync.wires {
            match wire {
                Some(w) => self.wires.insert(net, w),
                None => self.wires.remove(&net),
            };
        }
        for (id, unit) in sync.units {
            match unit {
                Some(u) => self.units.insert(id, u),
                None => self.units.remove(&id),
            };
        }
        if sync.tables_full {
            self.attach = Attach::default();
        }
        for (kind, layer, cell, value) in sync.cells {
            let key = (layer, cell);
            match (kind.as_str(), value) {
                ("open", Some(Value::Net(n))) => {
                    self.attach.open.insert(key, n);
                }
                ("routed", Some(Value::Net(n))) => {
                    self.attach.routed.insert(key, n);
                }
                ("ports", Some(Value::Cell(c))) => {
                    self.attach.ports.insert(key, c);
                }
                ("open", _) => {
                    self.attach.open.remove(&key);
                }
                ("routed", _) => {
                    self.attach.routed.remove(&key);
                }
                _ => {
                    self.attach.ports.remove(&key);
                }
            }
        }
        for (net, entries) in sync.entries {
            self.attach.entries.insert(net, entries);
        }
        for (net, pins) in sync.table_pins {
            if pins.is_empty() {
                self.attach.pins.remove(&net);
            } else {
                self.attach.pins.insert(net, pins);
            }
        }
        self.add_share(sync.share);
        self.unit_seq = sync.unit_seq;
        if placements {
            self.alternatives = self.alternatives_now();
        }
        if tables {
            self.open_by_layer = self.open_now();
        }
    }

    fn alternatives_now(&self) -> Map<String, Map<XY, Vec<(String, String)>>> {
        let mut out: Map<String, Map<XY, Vec<(String, String)>>> = Map::default();
        for (cell, placed) in &self.placed {
            for (pin, choices) in &placed.choices {
                let Some(id) = self.pin_id(cell, pin) else {
                    continue;
                };
                let Some(net) = self.pins.get(id).and_then(|p| self.nets.get(&p.net)) else {
                    continue;
                };
                let Some(carrier) = self.carriers.get(&net.carrier) else {
                    continue;
                };
                let by_cell = out.entry(carrier.layer.clone()).or_default();
                for (_, attach, _) in choices {
                    by_cell
                        .entry(*attach)
                        .or_default()
                        .push((cell.clone(), pin.clone()));
                }
            }
        }
        out
    }

    fn open_now(&self) -> Map<String, Vec<(XY, String)>> {
        let mut out: Map<String, Vec<(XY, String)>> = Map::default();
        for ((layer, xy), net) in &self.attach.open {
            out.entry(layer.clone())
                .or_default()
                .push((*xy, net.clone()));
        }
        for cells in out.values_mut() {
            cells.sort();
        }
        out
    }
}
