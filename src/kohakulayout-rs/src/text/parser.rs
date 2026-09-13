//! The pest entry point: text to statement records, mirroring the Lark transformer.

use pest::iterators::Pair;
use pest::Parser;
use pest_derive::Parser;

use super::moves::Step;
use super::stmt::{End, Opts, PortRec, RegionExpr, Seg, Stmt};
use super::values::{parse_value, unquote};
use crate::ir::geometry::XY;
use crate::ir::model::Attrs;
use crate::ir::rate::Rate;
use crate::{Error, Result};

#[derive(Parser)]
#[grammar = "kohakulayout-rs/src/text/kl.pest"]
pub struct KlParser;

type P<'i> = Pair<'i, Rule>;

fn xy(token: &str) -> XY {
    let (x, y) = token.split_once(',').unwrap();
    (x.parse().unwrap(), y.parse().unwrap())
}

fn size(token: &str) -> (i64, i64) {
    let (w, h) = token.split_once('x').unwrap();
    (w.parse().unwrap(), h.parse().unwrap())
}

fn rot(token: &str) -> i64 {
    token[1..].parse().unwrap()
}

fn text(pair: &P) -> String {
    pair.as_str().trim().to_string()
}

/// Options and attrs among a rule's children, the rest ignored.
fn opts_attrs(pairs: &[P]) -> (Opts, Attrs) {
    let mut opts = Opts::new();
    let mut attrs = Attrs::new();
    for pair in pairs {
        match pair.as_rule() {
            Rule::opt => {
                let mut inner = pair.clone().into_inner();
                let key = text(&inner.next().unwrap());
                let raw = inner.next().unwrap();
                let value = if raw.as_rule() == Rule::STRING {
                    serde_json::Value::String(unquote(raw.as_str()))
                } else {
                    parse_value(raw.as_str(), false)
                };
                opts.insert(key[..key.len() - 1].to_string(), value);
            }
            Rule::attr => {
                let mut inner = pair.clone().into_inner();
                let key = text(&inner.next().unwrap());
                let raw = inner.next().unwrap();
                let value = if raw.as_rule() == Rule::STRING {
                    serde_json::Value::String(unquote(raw.as_str()))
                } else {
                    parse_value(raw.as_str(), false)
                };
                let body = &key[1..key.len() - 1];
                let (ns, name) = body.split_once('.').unwrap();
                attrs
                    .entry(ns.to_string())
                    .or_default()
                    .insert(name.to_string(), value);
            }
            _ => {}
        }
    }
    (opts, attrs)
}

fn ids(pairs: &[P]) -> Vec<String> {
    pairs
        .iter()
        .filter(|p| p.as_rule() == Rule::ID)
        .map(text)
        .collect()
}

fn rate_of(pairs: &[P]) -> Option<Rate> {
    pairs
        .iter()
        .find(|p| p.as_rule() == Rule::rate)
        .and_then(|p| Rate::parse(p.as_str().trim()))
}

fn rect(pair: &P) -> (i64, i64, i64, i64) {
    let inner: Vec<P> = pair.clone().into_inner().collect();
    let (x, y) = xy(inner[0].as_str());
    let (w, h) = size(inner[1].as_str());
    (x, y, w, h)
}

fn endpoint(pair: &P) -> End {
    let inner = pair.clone().into_inner().next().unwrap();
    match inner.as_rule() {
        Rule::PINREF => End::Pin(text(&inner)),
        _ => End::Cell(xy(inner.into_inner().next().unwrap().as_str())),
    }
}

fn segment(pair: &P) -> Seg {
    let inner = pair.clone().into_inner().next().unwrap();
    let parts: Vec<P> = inner.clone().into_inner().collect();
    match inner.as_rule() {
        Rule::segment_cells => {
            let cells: Vec<XY> = parts
                .iter()
                .filter(|p| p.as_rule() == Rule::XY)
                .map(|p| xy(p.as_str()))
                .collect();
            Seg::Cells { cells, end: endpoint(parts.last().unwrap()) }
        }
        _ => {
            let start = endpoint(&parts[0]);
            let end = endpoint(parts.last().unwrap());
            let moves = parts[1..parts.len() - 1]
                .iter()
                .map(|p| {
                    let item = p.clone().into_inner().next().unwrap();
                    match item.as_rule() {
                        Rule::MOVE => {
                            let t = item.as_str();
                            Step::Move(t[..1].to_string(), t[1..].parse().unwrap())
                        }
                        _ => Step::Cell(xy(item.into_inner().next().unwrap().as_str())),
                    }
                })
                .collect();
            Seg::Moves { start, moves, end }
        }
    }
}

fn statement(pair: P) -> Option<Stmt> {
    let parts: Vec<P> = pair.clone().into_inner().collect();
    let rule = pair.as_rule();
    Some(match rule {
        Rule::header => Stmt::Header { version: parts[0].as_str().parse().unwrap() },
        Rule::physics => Stmt::Physics { id: text(&parts[0]) },
        Rule::fabric => {
            let (opts, attrs) = opts_attrs(&parts[1..]);
            Stmt::Fabric { size: size(parts[0].as_str()), opts, attrs }
        }
        Rule::region => {
            let (_, attrs) = opts_attrs(&parts[2..]);
            let expr_pair = parts[1].clone().into_inner().next().unwrap();
            let expr = match expr_pair.as_rule() {
                Rule::region_all => RegionExpr::All,
                Rule::region_not => RegionExpr::Not(
                    expr_pair
                        .into_inner()
                        .find(|p| p.as_rule() == Rule::ID)
                        .map(|p| text(&p))
                        .unwrap_or_default(),
                ),
                _ => RegionExpr::Rects(expr_pair.into_inner().map(|r| rect(&r)).collect()),
            };
            Stmt::Region { id: text(&parts[0]), expr, attrs }
        }
        Rule::carrier => {
            let (opts, attrs) = opts_attrs(&parts[2..]);
            Stmt::Carrier {
                id: text(&parts[0]),
                layer: text(&parts[1]),
                capacity: rate_of(&parts[2..]),
                opts,
                attrs,
            }
        }
        Rule::param => {
            let (opts, _) = opts_attrs(&parts);
            let (key, value) = opts.into_iter().next().unwrap();
            Stmt::Param { key, value }
        }
        Rule::cell => {
            let (opts, attrs) = opts_attrs(&parts[2..]);
            Stmt::Cell { id: text(&parts[0]), reference: text(&parts[1]), opts, attrs }
        }
        Rule::pin => {
            let (cell, pin) = parts[0].as_str().split_once('.').unwrap();
            let (opts, _) = opts_attrs(&parts[3..]);
            Stmt::Pin {
                cell: cell.to_string(),
                pin: pin.to_string(),
                direction: text(&parts[1]),
                carrier: text(&parts[2]),
                opts,
            }
        }
        Rule::net => {
            let (opts, attrs) = opts_attrs(&parts[2..]);
            let sources = parts
                .iter()
                .find(|p| p.as_rule() == Rule::net_sources)
                .map(|p| p.clone().into_inner().map(|r| text(&r)).collect())
                .unwrap_or_default();
            let sinks = parts
                .iter()
                .find(|p| p.as_rule() == Rule::net_sinks)
                .map(|p| p.clone().into_inner().map(|r| text(&r)).collect())
                .unwrap_or_default();
            Stmt::Net {
                id: text(&parts[0]),
                carrier: text(&parts[1]),
                rate: rate_of(&parts[2..]),
                opts,
                attrs,
                sources,
                sinks,
            }
        }
        Rule::group => {
            let (opts, attrs) = opts_attrs(&parts[1..]);
            Stmt::Group { id: text(&parts[0]), opts, attrs, members: ids(&parts[1..]) }
        }
        Rule::netattrs => {
            let (_, attrs) = opts_attrs(&parts);
            Stmt::Attrs { attrs }
        }
        Rule::layout_hdr => {
            let digest = parts
                .iter()
                .find(|p| p.as_rule() == Rule::DIGEST)
                .map(text)
                .unwrap_or_default();
            let (_, attrs) = opts_attrs(&parts);
            Stmt::Layout { digest, attrs }
        }
        Rule::place => Stmt::Place {
            cell: text(&parts[0]),
            xy: xy(parts[1].as_str()),
            rot: rot(parts[2].as_str()),
        },
        Rule::instance => Stmt::Instance {
            cell: text(&parts[0]),
            xy: xy(parts[1].as_str()),
            rot: rot(parts[2].as_str()),
        },
        Rule::wire => {
            let (opts, _) = opts_attrs(&parts[1..]);
            let segments = parts
                .iter()
                .filter(|p| p.as_rule() == Rule::segment)
                .map(segment)
                .collect();
            Stmt::Wire { net: text(&parts[0]), opts, segments }
        }
        Rule::unit => {
            let (opts, attrs) = opts_attrs(&parts[4..]);
            Stmt::Unit {
                id: text(&parts[0]),
                footprint: text(&parts[1]),
                xy: xy(parts[2].as_str()),
                rot: rot(parts[3].as_str()),
                opts,
                attrs,
            }
        }
        Rule::reserve => {
            let (opts, _) = opts_attrs(&parts[2..]);
            let rects = parts
                .iter()
                .filter(|p| p.as_rule() == Rule::rect)
                .map(rect)
                .collect();
            Stmt::Reserve { tag: text(&parts[0]), layer: text(&parts[1]), opts, rects }
        }
        Rule::assessment_hdr => Stmt::Assessment {
            digest: parts
                .iter()
                .find(|p| p.as_rule() == Rule::DIGEST)
                .map(text)
                .unwrap_or_default(),
        },
        Rule::metric => Stmt::Metric {
            name: text(&parts[0]),
            value: parse_value(parts[1].as_str().trim(), true),
        },
        Rule::finding => {
            let (_, attrs) = opts_attrs(&parts[4..]);
            Stmt::Finding {
                rule: text(&parts[0]),
                severity: text(&parts[1]),
                subject: text(&parts[2]),
                message: unquote(parts[3].as_str().trim()),
                attrs,
            }
        }
        Rule::complete => Stmt::Complete(parts[0].as_str().trim() == "true"),
        Rule::valid => Stmt::Valid(parts[0].as_str().trim() == "true"),
        Rule::lib => {
            let (opts, attrs) = opts_attrs(&parts[2..]);
            let ports = parts
                .iter()
                .filter(|p| p.as_rule() == Rule::port)
                .map(|p| {
                    let items: Vec<P> = p.clone().into_inner().collect();
                    let pos = items[3].as_str().trim();
                    let (_, pattrs) = opts_attrs(&items[4..]);
                    PortRec {
                        id: text(&items[0]),
                        direction: text(&items[1]),
                        carrier: text(&items[2]),
                        side: pos[..1].to_string(),
                        offset: pos[1..].parse().unwrap(),
                        attrs: pattrs,
                    }
                })
                .collect();
            Stmt::Lib { id: text(&parts[0]), size: size(parts[1].as_str()), opts, attrs, ports }
        }
        Rule::module => {
            let items = parts[1..]
                .iter()
                .filter_map(|p| statement(p.clone()))
                .collect();
            Stmt::Module { id: text(&parts[0]), items }
        }
        Rule::module_port => {
            let (cell, pin) = parts[3].as_str().trim().split_once('.').unwrap();
            Stmt::ModulePort {
                id: text(&parts[0]),
                direction: text(&parts[1]),
                carrier: text(&parts[2]),
                cell: cell.to_string(),
                pin: pin.to_string(),
            }
        }
        Rule::macro_ => {
            let items = parts[2..]
                .iter()
                .filter_map(|p| statement(p.clone()))
                .collect();
            Stmt::Macro { id: text(&parts[0]), module: text(&parts[1]), items }
        }
        _ => return None,
    })
}

/// The statement list of `text`, or a `Text` error naming the line.
pub fn parse_statements(source: &str) -> Result<Vec<Stmt>> {
    let mut owned = source.to_string();
    if !owned.ends_with('\n') {
        owned.push('\n');
    }
    let file = KlParser::parse(Rule::file, &owned).map_err(|e| {
        let (line, column) = match e.line_col {
            pest::error::LineColLocation::Pos((l, c)) => (l, c),
            pest::error::LineColLocation::Span((l, c), _) => (l, c),
        };
        let text = owned
            .lines()
            .nth(line.saturating_sub(1))
            .unwrap_or("")
            .trim()
            .to_string();
        Error::Text(format!("line {line}, column {column}: UnexpectedInput: {text}"))
    })?;
    let mut out = Vec::new();
    for pair in file {
        if pair.as_rule() != Rule::file {
            continue;
        }
        for stmt in pair.into_inner() {
            if stmt.as_rule() != Rule::statement {
                continue;
            }
            for inner in stmt.into_inner() {
                if let Some(record) = statement(inner) {
                    out.push(record);
                }
            }
        }
    }
    Ok(out)
}
