//! Wire paths as moves, cells and waypoints, and back again; Python's `moves.py`.

use crate::ir::geometry::{outward, XY};

#[derive(Clone, Debug)]
pub enum Step {
    Move(String, i64),
    Cell(XY),
}

pub fn cells_from_moves(start: XY, moves: &[Step]) -> Result<Vec<XY>, String> {
    let mut cells = vec![start];
    let (mut x, mut y) = start;
    for item in moves {
        match item {
            Step::Move(side, n) => {
                let (dx, dy) = outward(side);
                for _ in 0..*n {
                    x += dx;
                    y += dy;
                    cells.push((x, y));
                }
            }
            Step::Cell((tx, ty)) => {
                if *tx != x && *ty != y {
                    return Err(format!("waypoint @{tx},{ty} is not in line with ({x},{y})"));
                }
                let dx = (*tx > x) as i64 - (*tx < x) as i64;
                let dy = (*ty > y) as i64 - (*ty < y) as i64;
                while (x, y) != (*tx, *ty) {
                    x += dx;
                    y += dy;
                    cells.push((x, y));
                }
            }
        }
    }
    Ok(cells)
}

fn side_of(delta: XY) -> &'static str {
    match delta {
        (0, -1) => "N",
        (1, 0) => "E",
        (0, 1) => "S",
        _ => "W",
    }
}

pub fn moves_from_cells(cells: &[XY]) -> Vec<String> {
    let mut out = Vec::new();
    let mut run_side = "";
    let mut run = 0;
    for pair in cells.windows(2) {
        let side = side_of((pair[1].0 - pair[0].0, pair[1].1 - pair[0].1));
        if side == run_side {
            run += 1;
        } else {
            if run > 0 {
                out.push(format!("{run_side}{run}"));
            }
            run_side = side;
            run = 1;
        }
    }
    if run > 0 {
        out.push(format!("{run_side}{run}"));
    }
    out
}
