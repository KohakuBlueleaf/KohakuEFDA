//! The placement a search walks over, and what it costs: a mirror of
//! `kohakuefda.layout.heuristic.state`, held to it by a differential test.

/// A Gas Dispersing Unit makes a 13x13 zone (game-knowledge ENV-01).
const ZONE_SIDE: i32 = 13;

/// What each term of the cost is worth.
#[derive(Clone, Copy)]
pub struct Weights {
    pub area: f64,
    pub wire: f64,
    pub overlap: f64,
    pub group: f64,
    pub shut: f64,
    pub crowd: f64,
    pub tight: f64,
    pub slack: f64,
}

/// The cost split into what it is made of.
#[derive(Clone, Copy, Default, PartialEq, Debug)]
pub struct Terms {
    pub area: i64,
    pub wire: i64,
    pub overlap: i64,
    pub group: i64,
    pub shut: i64,
    pub crowd: f64,
}

/// What the terms are measured against, so the cost sits near one whatever the instance.
#[derive(Clone, Copy)]
pub struct Scale {
    pub area: f64,
    pub wire: f64,
}

pub struct Placement {
    pub count: usize,
    pub x: Vec<i32>,
    pub y: Vec<i32>,
    pub rotation: Vec<usize>,
    pub w: Vec<i32>,
    pub h: Vec<i32>,
    /// Footprint per block per rotation, as (width, height).
    pub size: Vec<[(i32, i32); 4]>,
    /// Pin offsets per block per rotation, flattened with `pin_at`.
    pub offset: Vec<[Vec<(i32, i32)>; 4]>,
    /// Free cells a block is entitled to on each side, per rotation: west, north, east, south.
    pub pad: Vec<[(i32, i32, i32, i32); 4]>,
    pub margin: Vec<i32>,
    pub extra: Vec<i32>,
    pub frozen: Vec<bool>,
    pub wire_from: Vec<(usize, usize)>,
    pub wire_to: Vec<(usize, usize)>,
    pub incident: Vec<Vec<usize>>,
    pub length: Vec<i64>,
    pub groups: Vec<Vec<usize>>,
    pub group_of: Vec<i32>,
    /// The gas unit of each group, or -1 when the group is a bus cluster.
    pub unit_of: Vec<i32>,
    pub area_rect: (i32, i32, i32, i32),
    pub heat: Vec<f64>,
    pub stride: i32,
    pub floor: i64,
    pub weights: Weights,
    pub scale: Scale,
    pub terms: Terms,
}

impl Placement {
    pub fn rect(&self, block: usize) -> (i32, i32, i32, i32) {
        (
            self.x[block],
            self.y[block],
            self.x[block] + self.w[block],
            self.y[block] + self.h[block],
        )
    }

    /// The area a block may stand in: the whole of it, less the border its group needs.
    pub fn room(&self, block: usize) -> (i32, i32, i32, i32) {
        let edge = self.margin[block];
        let (x0, y0, x1, y1) = self.area_rect;
        (x0 + edge, y0 + edge, x1 - edge, y1 - edge)
    }

    pub fn overlap(&self, a: usize, b: usize) -> i64 {
        let (ax0, ay0, ax1, ay1) = self.rect(a);
        let (bx0, by0, bx1, by1) = self.rect(b);
        let wide = ax1.min(bx1) - ax0.max(bx0);
        if wide <= 0 {
            return 0;
        }
        let high = ay1.min(by1) - ay0.max(by0);
        if high <= 0 {
            return 0;
        }
        (wide as i64) * (high as i64)
    }

    fn overlap_of(&self, block: usize) -> i64 {
        let mut total = 0;
        for other in 0..self.count {
            if other != block {
                total += self.overlap(block, other);
            }
        }
        total
    }

    /// Cells of one block's lane corridor the other stands on, both ways round.
    pub fn shut_pair(&self, a: usize, b: usize) -> i64 {
        let mut shut = 0;
        for (first, second) in [(a, b), (b, a)] {
            let (west, north, east, south) = self.pad[first][self.rotation[first]];
            let room = self.extra[first];
            let fx0 = self.x[first] - west - room;
            let fy0 = self.y[first] - north - room;
            let fx1 = self.x[first] + self.w[first] + east + room;
            let fy1 = self.y[first] + self.h[first] + south + room;
            let sx0 = self.x[second];
            let sy0 = self.y[second];
            let wide = fx1.min(sx0 + self.w[second]) - fx0.max(sx0);
            if wide <= 0 {
                continue;
            }
            let high = fy1.min(sy0 + self.h[second]) - fy0.max(sy0);
            if high > 0 {
                shut += (wide as i64) * (high as i64);
            }
        }
        shut - 2 * self.overlap(a, b)
    }

    fn shut_of(&self, block: usize) -> i64 {
        let mut total = 0;
        for other in 0..self.count {
            if other != block {
                total += self.shut_pair(block, other);
            }
        }
        total
    }

    fn crowd_of(&self, block: usize) -> f64 {
        let mut total = 0.0;
        for row in self.y[block]..self.y[block] + self.h[block] {
            let base = row * self.stride;
            for column in self.x[block]..self.x[block] + self.w[block] {
                let index = (base + column) as usize;
                if index < self.heat.len() {
                    total += self.heat[index];
                }
            }
        }
        total
    }

    fn outside(&self, block: usize) -> i64 {
        let (x0, y0, x1, y1) = self.rect(block);
        let (ax0, ay0, ax1, ay1) = self.room(block);
        let over = (ax0 - x0).max(0) + (x1 - ax1).max(0);
        let down = (ay0 - y0).max(0) + (y1 - ay1).max(0);
        (over as i64) * ((y1 - y0) as i64) + (down as i64) * ((x1 - x0) as i64)
    }

    fn gap(&self, a: usize, b: usize) -> i64 {
        let (ax0, ay0, ax1, ay1) = self.rect(a);
        let (bx0, by0, bx1, by1) = self.rect(b);
        let wide = (bx0 - ax1).max(ax0 - bx1).max(0);
        let high = (by0 - ay1).max(ay0 - by1).max(0);
        (wide + high) as i64
    }

    /// Cells of a machine that fall outside its gas unit's zone (ENV-02).
    fn loose(&self, block: usize, unit: usize) -> i64 {
        let half = ZONE_SIDE / 2;
        let cx = self.x[unit] + self.w[unit] / 2;
        let cy = self.y[unit] + self.h[unit] / 2;
        let (zx0, zy0) = (cx - half, cy - half);
        let (zx1, zy1) = (cx + half + 1, cy + half + 1);
        let (x0, y0, x1, y1) = self.rect(block);
        let over = (zx0 - x0).max(0) + (x1 - zx1).max(0);
        let down = (zy0 - y0).max(0) + (y1 - zy1).max(0);
        (over as i64) * ((y1 - y0) as i64) + (down as i64) * ((x1 - x0) as i64)
    }

    fn group_fault(&self, members: &[usize]) -> i64 {
        if members.len() < 2 {
            return 0;
        }
        let unit = self.unit_of[self.group_of[members[0]] as usize];
        if unit >= 0 {
            return members
                .iter()
                .filter(|&&m| m != unit as usize)
                .map(|&m| self.loose(m, unit as usize))
                .sum();
        }
        let mut spread = 0;
        for (i, &first) in members.iter().enumerate() {
            let mut best = i64::MAX;
            for (j, &second) in members.iter().enumerate() {
                if i != j {
                    best = best.min(self.gap(first, second));
                }
            }
            spread += best;
        }
        spread
    }

    fn faults(&self) -> i64 {
        let mut total = 0;
        for block in 0..self.count {
            total += self.outside(block);
        }
        for members in &self.groups {
            total += self.group_fault(members);
        }
        total
    }

    pub fn span(&self, wire: usize) -> i64 {
        let (source, source_slot) = self.wire_from[wire];
        let (sink, sink_slot) = self.wire_to[wire];
        let here = self.offset[source][self.rotation[source]][source_slot];
        let there = self.offset[sink][self.rotation[sink]][sink_slot];
        let across = (self.x[source] + here.0) - (self.x[sink] + there.0);
        let down = (self.y[source] + here.1) - (self.y[sink] + there.1);
        (across.abs() + down.abs()) as i64
    }

    fn bbox(&self) -> i64 {
        let mut x0 = i32::MAX;
        let mut y0 = i32::MAX;
        let mut x1 = i32::MIN;
        let mut y1 = i32::MIN;
        for block in 0..self.count {
            x0 = x0.min(self.x[block]);
            y0 = y0.min(self.y[block]);
            x1 = x1.max(self.x[block] + self.w[block]);
            y1 = y1.max(self.y[block] + self.h[block]);
        }
        ((x1 - x0) as i64) * ((y1 - y0) as i64)
    }

    /// Every term rebuilt from the anchors: the oracle the incremental update is held to.
    pub fn recompute(&mut self) {
        let mut terms = Terms { area: self.bbox(), ..Default::default() };
        for wire in 0..self.wire_from.len() {
            self.length[wire] = self.span(wire);
        }
        terms.wire = self.length.iter().sum();
        for a in 0..self.count {
            for b in a + 1..self.count {
                terms.overlap += self.overlap(a, b);
                terms.shut += self.shut_pair(a, b);
            }
        }
        terms.group = self.faults();
        for block in 0..self.count {
            terms.crowd += self.crowd_of(block);
        }
        self.terms = terms;
    }

    /// Move one block and fold the change into the running cost.
    pub fn put(&mut self, block: usize, x: i32, y: i32, rotation: usize) {
        let before_overlap = self.overlap_of(block);
        let before_shut = self.shut_of(block);
        let before_crowd = self.crowd_of(block);
        let mut before_fault = self.outside(block);
        let group = self.group_of[block];
        if group >= 0 {
            before_fault += self.group_fault(&self.groups[group as usize].clone());
        }
        let was: Vec<i64> = self.incident[block]
            .iter()
            .map(|&wire| self.length[wire])
            .collect();
        self.x[block] = x;
        self.y[block] = y;
        self.rotation[block] = rotation;
        let (width, height) = self.size[block][rotation];
        self.w[block] = width;
        self.h[block] = height;
        self.terms.overlap += self.overlap_of(block) - before_overlap;
        self.terms.shut += self.shut_of(block) - before_shut;
        self.terms.crowd += self.crowd_of(block) - before_crowd;
        let mut after_fault = self.outside(block);
        if group >= 0 {
            after_fault += self.group_fault(&self.groups[group as usize].clone());
        }
        self.terms.group += after_fault - before_fault;
        let wires = self.incident[block].clone();
        for (slot, wire) in wires.iter().enumerate() {
            let span = self.span(*wire);
            self.terms.wire += span - was[slot];
            self.length[*wire] = span;
        }
        self.terms.area = self.bbox();
    }

    /// What the placement costs, with the floor its lanes will need charged for.
    pub fn cost(&self) -> f64 {
        let w = &self.weights;
        let mut total = w.area * self.terms.area as f64 / self.scale.area
            + w.wire * self.terms.wire as f64 / self.scale.wire
            + w.overlap * self.terms.overlap as f64 / self.scale.area
            + w.group * self.terms.group as f64 / self.scale.wire
            + w.shut * self.terms.shut as f64
            + w.crowd * self.terms.crowd;
        let needed = self.terms.wire as f64 * w.slack;
        let spare = self.terms.area as f64 - self.floor as f64 - needed;
        if spare < 0.0 {
            total -= w.tight * spare / self.scale.wire;
        }
        total
    }

    pub fn rescale(&mut self) {
        self.scale = Scale {
            area: (self.terms.area as f64).max(1.0),
            wire: (self.terms.wire as f64).max(1.0),
        };
    }

    /// An anchor kept where the whole footprint stands in the block's room.
    pub fn inside(&self, block: usize, x: i32, y: i32, rotation: usize) -> (i32, i32) {
        let (width, height) = self.size[block][rotation];
        let (x0, y0, x1, y1) = self.room(block);
        (x.max(x0).min((x1 - width).max(x0)), y.max(y0).min((y1 - height).max(y0)))
    }
}
