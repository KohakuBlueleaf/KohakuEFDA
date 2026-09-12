//! One net's lanes laid natively, the twin of `lay` in `state/router/lanes.py`: the policy's
//! lanes in order, each from its source pin's own lanes or open attach cells to its sink pin's,
//! the blocking lanes taken up once, the search over the classified layer, the plan assembled.
//! A case the twin cannot answer comes back as an error.

use std::collections::BTreeSet;

use super::astar::{find, Ask, Scratch};
use super::grid::{Grid, XY};
use super::hash::Set;
use super::judge::{crossable_own, single_cell, Regions};
use super::lanes::{list_text, xy_text, Lane};
use super::plan::Lay;
use super::spec::Doc;
use super::tables::Tables;

/// What a lay answers.
pub enum Answer {
    Plan {
        segments: Vec<Vec<XY>>,
        crossings: Vec<(XY, String, bool)>,
        junctions: Vec<(XY, String)>,
        rips: Vec<String>,
        displaced: Vec<String>,
        ports: Vec<(String, String)>,
    },
    Refused {
        detail: String,
    },
}

/// Which lanes the worklist lays: all, the one named, or only those laid again.
enum Filter {
    Every,
    Lane(Lane),
    Again,
}

/// Lay the document's lanes: the plan or the refusal; an error when the twin cannot answer.
pub fn lay(
    grid: &Grid,
    tables: &Tables,
    regions: &Regions,
    doc: &Doc,
    ask: &Ask<'_>,
    scratch: &mut Scratch,
) -> Result<Answer, String> {
    let mut l = Lay::new(doc, grid, tables, regions);
    if let Some(seed) = &doc.seed {
        if !seed.segments.is_empty() {
            l.absorb(seed.segments.clone())?;
        }
    }
    let mut queue: Vec<Lane> = doc.policy.lanes.clone();
    let mut again: Set<Lane> = Set::default();
    let mut forced: Set<Lane> = Set::default();
    let mut filter = match &doc.only {
        Some(lane) => Filter::Lane(lane.clone()),
        None => Filter::Every,
    };
    let mut position = 0;
    while position < queue.len() {
        let lane = queue[position].clone();
        position += 1;
        let (source, sink) = (&lane.0, &lane.1);
        if l.has_pin(source, sink) {
            continue;
        }
        let skip = match &filter {
            Filter::Every => false,
            Filter::Lane(only) => *only != lane && !again.contains(&lane),
            Filter::Again => !again.contains(&lane),
        };
        if skip {
            continue;
        }
        let a = l.by_ref.get(source.as_str()).copied();
        let b = l.by_ref.get(sink.as_str()).copied();
        let (Some(a), Some(b)) = (a, b) else {
            continue;
        };
        let (first, source_tree) = l.ends(a, 0)?;
        let (goals_in, sink_tree) = l.ends(b, 1)?;
        let mut starts: Set<XY> = first.iter().cloned().collect();
        let mut goals: Set<XY> = goals_in.iter().cloned().collect();
        if (starts.is_empty() || goals.is_empty()) && !forced.contains(&lane) {
            forced.insert(lane.clone());
            let victims: Vec<Lane> = l
                .blockers(source, sink)?
                .into_iter()
                .filter(|(s, t)| l.has_pin(s, t))
                .collect();
            if !victims.is_empty() {
                let keep: Vec<Vec<XY>> = l
                    .segments
                    .iter()
                    .zip(&l.pins)
                    .filter(|(_, (s, t))| {
                        !victims.iter().any(|(vs, vt)| {
                            s.as_deref() == Some(vs.as_str()) && t.as_deref() == Some(vt.as_str())
                        })
                    })
                    .map(|(seg, _)| seg.clone())
                    .collect();
                l.absorb(keep)?;
                let gone: Vec<Lane> = queue[..position - 1]
                    .iter()
                    .filter(|(s, t)| !l.has_pin(s, t))
                    .cloned()
                    .collect();
                again.extend(gone.iter().cloned());
                let rest: Set<Lane> = queue[position..].iter().cloned().collect();
                let insert: Vec<Lane> = gone.into_iter().filter(|p| !rest.contains(p)).collect();
                queue.splice(position..position, insert);
                position -= 1;
                continue;
            }
        }
        if starts.is_empty() || goals.is_empty() {
            let side = if starts.is_empty() {
                "start from"
            } else {
                "end on"
            };
            let detail = format!("lane {source}>{sink} has no cell to {side}");
            return Ok(Answer::Refused { detail });
        }
        let tree_cells: Set<XY> = l.segments.iter().flatten().cloned().collect();
        let reserved: Set<XY> = doc
            .terminals
            .iter()
            .filter(|t| t.bound && t.id != a.id && t.id != b.id)
            .filter_map(|t| t.options.first().map(|o| o.1))
            .collect();
        starts.retain(|c| !reserved.contains(c));
        goals.retain(|c| !reserved.contains(c));
        if starts.is_empty() || goals.is_empty() {
            let detail = format!("lane {source}>{sink} has only reserved cells");
            return Ok(Answer::Refused { detail });
        }
        let crossable = crossable_own(
            grid,
            &doc.layer,
            &l.segments,
            &l.junction_cells(),
            &l.crossed,
            &l.behind,
        );
        let mut owned: Vec<(XY, u8)> = crossable
            .into_iter()
            .filter(|(c, _)| !source_tree.contains(c) && !sink_tree.contains(c))
            .collect();
        owned.sort();
        let owned_cells: Set<XY> = owned.iter().map(|(c, _)| *c).collect();
        let both: BTreeSet<XY> = starts.intersection(&goals).cloned().collect();
        let cells: Vec<XY> = if !both.is_empty() {
            let found = single_cell(
                grid,
                tables,
                regions,
                &doc.carrier,
                &doc.net,
                &doc.layer,
                a.at,
                &both,
                &mut l.crossings,
            )
            .ok_or("a crossing unit not registered")?;
            let Some(cell) = found else {
                let detail = format!("lane {source}>{sink}: its only cell is held");
                return Ok(Answer::Refused { detail });
            };
            filter = Filter::Again;
            let joins = source_tree.contains(&cell) || sink_tree.contains(&cell);
            if !doc.policy.single_joins && joins {
                let detail = format!("lane {source}>{sink} would be one cell");
                return Ok(Answer::Refused { detail });
            }
            vec![cell]
        } else {
            let mut starts_in: Vec<XY> = Vec::new();
            let mut used = Set::default();
            for c in &first {
                if starts.contains(c) {
                    starts_in.push(*c);
                    used.insert(*c);
                }
            }
            let mut rest: Vec<XY> = starts
                .iter()
                .filter(|c| !used.contains(*c))
                .cloned()
                .collect();
            rest.sort();
            starts_in.extend(rest);
            let mut targets: Vec<XY> = goals.iter().cloned().collect();
            targets.sort();
            let avoid: Vec<XY> = tree_cells
                .iter()
                .filter(|c| !starts.contains(c) && !goals.contains(c) && !owned_cells.contains(c))
                .chain(reserved.iter())
                .cloned()
                .collect::<BTreeSet<XY>>()
                .into_iter()
                .collect();
            let own_list: Vec<(i64, i64, u8)> =
                owned.iter().map(|((x, y), axis)| (*x, *y, *axis)).collect();
            let searched = find(grid, &starts_in, &targets, &avoid, &own_list, ask, scratch);
            match searched {
                None => {
                    let low = starts.iter().min().copied().ok_or("no start")?;
                    let shown: Vec<XY> = targets.iter().take(4).cloned().collect();
                    let detail = format!(
                        "no path for lane {source}>{sink} from {} to any of {}",
                        xy_text(low),
                        list_text(&shown)
                    );
                    return Ok(Answer::Refused { detail });
                }
                Some(found) => {
                    for (xy, _, _) in &found.crossings {
                        l.crossed.insert(*xy);
                    }
                    l.crossings.extend(found.crossings);
                    l.rips.extend(found.rips);
                    l.displaced.extend(found.displaces);
                    found.cells
                }
            }
        };
        let (head, tail) = (cells[0], cells[cells.len() - 1]);
        if source_tree.contains(&head) {
            l.set_junction(head, "split");
        } else {
            l.took(a, head)?;
        }
        if sink_tree.contains(&tail) {
            l.set_junction(tail, "merge");
        } else {
            l.took(b, tail)?;
        }
        let crossed: Vec<XY> = l.crossings.iter().map(|(xy, _, _)| *xy).collect();
        l.crossed.extend(crossed);
        l.segments.push(cells);
        l.pins.push((Some(source.clone()), Some(sink.clone())));
    }
    Ok(Answer::Plan {
        segments: l.segments,
        crossings: l.crossings,
        junctions: l.junctions,
        rips: l.rips.into_iter().collect(),
        displaced: l.displaced.into_iter().collect(),
        ports: l.ports,
    })
}
