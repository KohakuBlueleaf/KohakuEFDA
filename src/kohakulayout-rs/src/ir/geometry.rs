//! Grid geometry: sides, rotations, footprint cells, port and attach cells, rectangle covers.

use serde::{Deserialize, Serialize};

pub type XY = (i64, i64);
pub const SIDES: [&str; 4] = ["N", "E", "S", "W"];
pub const ROTATIONS: [i64; 4] = [0, 90, 180, 270];

pub fn outward(side: &str) -> XY {
    match side {
        "N" => (0, -1),
        "E" => (1, 0),
        "S" => (0, 1),
        _ => (-1, 0),
    }
}

pub fn rotate_size(width: i64, height: i64, rot: i64) -> XY {
    if rot == 0 || rot == 180 {
        (width, height)
    } else {
        (height, width)
    }
}

pub fn rotate_side(side: &str, rot: i64) -> &'static str {
    let index = SIDES.iter().position(|s| *s == side).unwrap_or(0);
    SIDES[((index as i64 + rot / 90).rem_euclid(4)) as usize]
}

pub fn rotate_point(px: i64, py: i64, width: i64, height: i64, rot: i64) -> XY {
    match rot {
        0 => (px, py),
        90 => (height - 1 - py, px),
        180 => (width - 1 - px, height - 1 - py),
        _ => (py, width - 1 - px),
    }
}

pub fn port_cell(width: i64, height: i64, side: &str, offset: i64, rot: i64) -> XY {
    let (px, py) = match side {
        "N" => (offset, 0),
        "S" => (offset, height - 1),
        "W" => (0, offset),
        _ => (width - 1, offset),
    };
    rotate_point(px, py, width, height, rot)
}

pub fn attach_cell(width: i64, height: i64, side: &str, offset: i64, rot: i64) -> XY {
    let (cx, cy) = port_cell(width, height, side, offset, rot);
    let (dx, dy) = outward(rotate_side(side, rot));
    (cx + dx, cy + dy)
}

pub fn footprint_cells(x: i64, y: i64, width: i64, height: i64, rot: i64) -> Vec<XY> {
    let (rw, rh) = rotate_size(width, height, rot);
    let mut out = Vec::with_capacity((rw * rh) as usize);
    for j in 0..rh {
        for i in 0..rw {
            out.push((x + i, y + j));
        }
    }
    out
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Rect {
    pub x: i64,
    pub y: i64,
    pub w: i64,
    pub h: i64,
}

impl Rect {
    pub fn cells(&self) -> Vec<XY> {
        let mut out = Vec::new();
        for j in 0..self.h {
            for i in 0..self.w {
                out.push((self.x + i, self.y + j));
            }
        }
        out
    }
}

/// The canonical rectangle cover Python's `rects_from_cells` produces: row runs merged downwards while identical.
pub fn rects_from_cells(cells: &std::collections::BTreeSet<XY>) -> Vec<Rect> {
    use std::collections::BTreeMap;
    let mut rows: BTreeMap<i64, Vec<i64>> = BTreeMap::new();
    for (x, y) in cells {
        rows.entry(*y).or_default().push(*x);
    }
    let mut runs: Vec<(i64, i64, i64)> = Vec::new();
    for (y, xs) in rows.iter_mut() {
        xs.sort_unstable();
        let mut start = xs[0];
        let mut prev = xs[0];
        for &x in &xs[1..] {
            if x != prev + 1 {
                runs.push((*y, start, prev - start + 1));
                start = x;
            }
            prev = x;
        }
        runs.push((*y, start, prev - start + 1));
    }
    let mut rects: Vec<Rect> = Vec::new();
    let mut open_below: BTreeMap<(i64, i64), usize> = BTreeMap::new();
    for (y, x, w) in runs {
        match open_below.get(&(x, w)) {
            Some(&index) if rects[index].y + rects[index].h == y => {
                rects[index].h += 1;
            }
            _ => {
                rects.push(Rect { x, y, w, h: 1 });
                open_below.insert((x, w), rects.len() - 1);
            }
        }
    }
    rects.sort_by_key(|r| (r.y, r.x));
    rects
}
