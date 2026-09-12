//! What a native lay reads off standing lanes: the pin behind each attach cell, each segment's
//! source and sink pin, the segments that still read as whole lanes, the lanes that laid enough
//! cells of their own, a tree's trunk among a pin's lanes; and the text of a refusal's cells.

use super::grid::XY;
use super::hash::{Map, Set};
use super::spec::Terminal;

/// A segment's source and sink pin, either unknown.
pub(super) type Pair = (Option<String>, Option<String>);
/// A lane's source and sink pin.
pub(super) type Lane = (String, String);

pub(super) fn get<'v>(pairs: &'v [(String, String)], key: &str) -> Option<&'v str> {
    pairs
        .iter()
        .find(|(k, _)| k == key)
        .map(|(_, v)| v.as_str())
}

pub(super) fn put(pairs: &mut Vec<(String, String)>, key: &str, value: &str) {
    match pairs.iter_mut().find(|(k, _)| k == key) {
        Some(entry) => entry.1 = value.to_string(),
        None => pairs.push((key.to_string(), value.to_string())),
    }
}

pub(super) fn xy_text(xy: XY) -> String {
    format!("({}, {})", xy.0, xy.1)
}

pub(super) fn list_text(cells: &[XY]) -> String {
    let parts: Vec<String> = cells.iter().map(|c| xy_text(*c)).collect();
    format!("[{}]", parts.join(", "))
}

/// The pin behind each attach cell a standing lane may end on; bound and recorded ports win.
pub(super) fn attach_pins(terminals: &[Terminal], ports: &[(String, String)]) -> Map<XY, String> {
    let mut at = Map::default();
    for t in terminals {
        if !t.bound && get(ports, &t.id).is_none() {
            for (_, attach) in &t.options {
                at.insert(*attach, t.id.clone());
            }
        }
    }
    for t in terminals {
        let recorded = get(ports, &t.id);
        for (port, attach) in &t.options {
            if t.bound || Some(port.as_str()) == recorded {
                at.insert(*attach, t.id.clone());
            }
        }
    }
    at
}

/// Every standing segment's source and sink pin, read from its ends and the segments it ends on.
#[allow(clippy::needless_range_loop)]
pub(super) fn lane_pins(runs: &[Vec<XY>], at: &Map<XY, String>, sources: &Set<&str>) -> Vec<Pair> {
    let mut pins: Vec<[Option<String>; 2]> = runs
        .iter()
        .map(|run| {
            let head = at.get(&run[0]).filter(|p| sources.contains(p.as_str()));
            let tail = at
                .get(&run[run.len() - 1])
                .filter(|p| !sources.contains(p.as_str()));
            [head.cloned(), tail.cloned()]
        })
        .collect();
    let mut changed = true;
    while changed {
        changed = false;
        for i in 0..runs.len() {
            for side in 0..2 {
                let end = if side == 0 {
                    runs[i][0]
                } else {
                    runs[i][runs[i].len() - 1]
                };
                if pins[i][side].is_some() {
                    continue;
                }
                for j in 0..runs.len() {
                    if j != i && runs[j].contains(&end) && pins[j][side].is_some() {
                        pins[i][side] = pins[j][side].clone();
                        changed = true;
                        break;
                    }
                }
            }
        }
    }
    pins.into_iter().map(|[a, b]| (a, b)).collect()
}

/// The standing segments that still read as whole lanes, with their pins.
pub(super) fn whole_lanes(
    segments: Vec<Vec<XY>>,
    at: &Map<XY, String>,
    sources: &Set<&str>,
) -> (Vec<Vec<XY>>, Vec<Pair>) {
    let mut kept = segments;
    while !kept.is_empty() {
        let read = lane_pins(&kept, at, sources);
        let whole: Vec<Vec<XY>> = kept
            .iter()
            .zip(&read)
            .filter(|(_, (s, t))| s.is_some() && t.is_some())
            .map(|(seg, _)| seg.clone())
            .collect();
        if whole.len() == kept.len() {
            return (kept, read);
        }
        kept = whole;
    }
    (Vec::new(), Vec::new())
}

/// Which runs laid at least `minimum` cells of their own; an end on an earlier run is not its own.
pub(super) fn laid_enough(segments: &[Vec<XY>], minimum: usize) -> Vec<bool> {
    let mut out = Vec::new();
    for (i, run) in segments.iter().enumerate() {
        let others: Set<XY> = segments[..i].iter().flatten().cloned().collect();
        let mut own = run.len() as i64;
        if others.contains(&run[0]) {
            own -= 1;
        }
        if run.len() > 1 && others.contains(&run[run.len() - 1]) {
            own -= 1;
        }
        out.push(own >= minimum as i64);
    }
    out
}

/// The trunk among the lanes: the first when none are named, else the lane between the ends.
pub(super) fn trunk_index(lanes: &[&Pair], root: &str, main: &str) -> Option<usize> {
    if lanes.is_empty() {
        return Some(0);
    }
    lanes
        .iter()
        .position(|(s, t)| s.as_deref() == Some(root) && t.as_deref() == Some(main))
}
