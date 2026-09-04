//! The grid and the search, with no Python in them.

use std::collections::BinaryHeap;
use std::collections::HashMap;

pub const GROUND: usize = 0;
pub const SKY: usize = 1;
pub const LAYERS: usize = 2;
pub const AXIS_NONE: u8 = 0;
pub const AXIS_H: u8 = 1;
pub const AXIS_V: u8 = 2;
pub const AXIS_T: u8 = 3;
/// Step order matches `pathfinder.STEPS`: north, east, south, west.
pub const STEPS: [(i32, i32); 4] = [(0, -1), (1, 0), (0, 1), (-1, 0)];
const OPPOSITE: [usize; 4] = [2, 3, 0, 1];
/// The direction a state was entered by, or `NO_DIR` for one a path starts at.
const NO_DIR: usize = 4;
const DIRS: usize = NO_DIR + 1;

/// One layer's occupancy. Two holders per cell is every legal case: a third is an overuse the
/// caller refuses before it reaches here.
#[derive(Clone, Default)]
pub struct Cells {
    pub blocked: Vec<bool>,
    /// A machine's own footprint, as against the ring and the fixed depot, which block a lane
    /// but are not part of the line the layout is measured by.
    pub owned: Vec<bool>,
    pub unit: Vec<bool>,
    pub history: Vec<f32>,
    pub holder: Vec<[i32; 2]>,
    pub axis: Vec<[u8; 2]>,
    pub count: Vec<u8>,
    pub reserved: HashMap<usize, Vec<i32>>,
}

impl Cells {
    pub fn new(size: usize) -> Self {
        Cells {
            blocked: vec![false; size],
            owned: vec![false; size],
            unit: vec![false; size],
            history: vec![0.0; size],
            holder: vec![[-1, -1]; size],
            axis: vec![[AXIS_NONE, AXIS_NONE]; size],
            count: vec![0; size],
            reserved: HashMap::new(),
        }
    }

    fn holds(&self, index: usize, wire: i32) -> bool {
        (0..self.count[index].min(2) as usize).any(|slot| self.holder[index][slot] == wire)
    }

    /// How many other wires hold the cell, and the axis of the single one when there is one.
    fn others(&self, index: usize, wire: i32) -> (u8, u8) {
        let held = self.count[index];
        if held == 0 {
            return (0, AXIS_NONE);
        }
        let mine = if self.holds(index, wire) { 1 } else { 0 };
        let mut axis = AXIS_NONE;
        for slot in 0..held.min(2) as usize {
            if self.holder[index][slot] != wire {
                axis = self.axis[index][slot];
            }
        }
        (held - mine, axis)
    }

    /// Every other wire on a reserved cell is one the reservation names, which is what lets a
    /// bridge stand on the cell a port faces.
    fn all_owned(&self, index: usize, wire: i32, owners: &[i32]) -> bool {
        let mut any = false;
        for slot in 0..self.count[index].min(2) as usize {
            let holder = self.holder[index][slot];
            if holder != wire {
                any = true;
                if !owners.contains(&holder) {
                    return false;
                }
            }
        }
        any && self.count[index] <= 2
    }
}

#[derive(PartialEq)]
struct Node {
    estimate: f32,
    order: u32,
    index: usize,
    direction: usize,
    crossing: bool,
}

impl Eq for Node {}

impl Ord for Node {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        other
            .estimate
            .partial_cmp(&self.estimate)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| other.order.cmp(&self.order))
    }
}

impl PartialOrd for Node {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

/// What a search may leave a start by or enter a goal by: a bitmask over `STEPS`, 0 for any.
pub type Ends = Vec<(i32, i32, u8)>;

pub struct Search<'a> {
    pub layer: usize,
    pub wire: i32,
    pub starts: &'a Ends,
    pub goals: &'a Ends,
    pub present_cost: f32,
    pub share: bool,
    pub limit: f32,
    /// Goal cells another wire may already hold, `None` when every goal may be shared.
    pub shared: Option<&'a Vec<(i32, i32)>>,
}

pub struct Grid {
    pub width: usize,
    pub height: usize,
    pub turn_cost: f32,
    pub bridge_cost: f32,
    pub history_cost: f32,
    pub layers: [Cells; LAYERS],
}

impl Grid {
    pub fn new(
        width: usize,
        height: usize,
        turn_cost: f32,
        bridge_cost: f32,
        history_cost: f32,
    ) -> Self {
        let size = width * height;
        Grid {
            width,
            height,
            turn_cost,
            bridge_cost,
            history_cost,
            layers: [Cells::new(size), Cells::new(size)],
        }
    }

    pub fn index(&self, x: i32, y: i32) -> Option<usize> {
        if x < 0 || y < 0 || x as usize >= self.width || y as usize >= self.height {
            None
        } else {
            Some(y as usize * self.width + x as usize)
        }
    }

    pub fn cell(&self, index: usize) -> (i32, i32) {
        ((index % self.width) as i32, (index / self.width) as i32)
    }

    pub fn hold(&mut self, layer: usize, index: usize, wire: i32, axis: u8) {
        let side = &mut self.layers[layer];
        for slot in 0..side.count[index].min(2) as usize {
            if side.holder[index][slot] == wire {
                side.axis[index][slot] = axis;
                return;
            }
        }
        let slot = side.count[index] as usize;
        if slot < 2 {
            side.holder[index][slot] = wire;
            side.axis[index][slot] = axis;
        }
        side.count[index] = side.count[index].saturating_add(1);
    }

    /// One wire lets a cell go. A wire that never held it changes nothing: the caller may ask
    /// for a release it is not sure of, and must not cost another wire its place.
    pub fn release(&mut self, layer: usize, index: usize, wire: i32) {
        let side = &mut self.layers[layer];
        for slot in 0..side.count[index].min(2) as usize {
            if side.holder[index][slot] == wire {
                side.holder[index][slot] = side.holder[index][1];
                side.axis[index][slot] = side.axis[index][1];
                side.holder[index][1] = -1;
                side.axis[index][1] = AXIS_NONE;
                side.count[index] = side.count[index].saturating_sub(1);
                return;
            }
        }
    }

    /// Whether the line uses a cell at all: a machine, a lane, or a junction, on either layer.
    pub fn used(&self, index: usize) -> bool {
        self.layers
            .iter()
            .any(|side| side.owned[index] || side.unit[index] || side.count[index] > 0)
    }

    /// The rectangle the line needs, or `None` when nothing is placed.
    pub fn extent(&self) -> Option<(i32, i32, i32, i32)> {
        let (mut x0, mut y0, mut x1, mut y1) = (i32::MAX, i32::MAX, i32::MIN, i32::MIN);
        for index in 0..self.width * self.height {
            if self.used(index) {
                let (x, y) = self.cell(index);
                x0 = x0.min(x);
                y0 = y0.min(y);
                x1 = x1.max(x + 1);
                y1 = y1.max(y + 1);
            }
        }
        if x0 > x1 {
            None
        } else {
            Some((x0, y0, x1, y1))
        }
    }

    /// The first square of `size` the line leaves free inside the window, or `None`.
    pub fn free_square(
        &self,
        window: (i32, i32, i32, i32),
        size: i32,
        taken: &[(i32, i32)],
    ) -> Option<(i32, i32)> {
        for py in window.1..window.3 {
            'anchor: for px in window.0..window.2 {
                for dy in 0..size {
                    for dx in 0..size {
                        if taken.contains(&(px + dx, py + dy)) {
                            continue 'anchor;
                        }
                        match self.index(px + dx, py + dy) {
                            Some(index) if !self.used(index) => {}
                            _ => continue 'anchor,
                        }
                    }
                }
                return Some((px, py));
            }
        }
        None
    }

    /// A pipe unit stands here: a junction, or the bridge two pipe holders make.
    fn pipe_unit(&self, index: usize) -> bool {
        let sky = &self.layers[SKY];
        sky.unit[index] || sky.count[index] == 2
    }

    /// The ground under a sky cell is clear of buildings and belts.
    fn ground_free(&self, index: usize) -> bool {
        let ground = &self.layers[GROUND];
        !ground.blocked[index] && ground.count[index] == 0
    }

    /// The cheapest path from any start to any goal, cell for cell as the Python A* finds it.
    pub fn astar(&self, search: &Search) -> Option<Vec<(i32, i32)>> {
        if search.starts.is_empty() || search.goals.is_empty() {
            return None;
        }
        let size = self.width * self.height;
        let mut goal_mask = vec![0u8; size];
        let mut is_goal = vec![false; size];
        let (mut gx0, mut gx1, mut gy0, mut gy1) = (i32::MAX, i32::MIN, i32::MAX, i32::MIN);
        for &(x, y, mask) in search.goals {
            let Some(index) = self.index(x, y) else {
                continue;
            };
            goal_mask[index] = mask;
            is_goal[index] = true;
            gx0 = gx0.min(x);
            gx1 = gx1.max(x);
            gy0 = gy0.min(y);
            gy1 = gy1.max(y);
        }
        if gx0 > gx1 {
            return None;
        }
        let mut attach = vec![search.shared.is_none(); size];
        if let Some(cells) = search.shared {
            for &(x, y) in cells {
                if let Some(index) = self.index(x, y) {
                    attach[index] = true;
                }
            }
        }
        let mut start_mask = vec![0u8; size];
        let mut is_start = vec![false; size];
        let mut shared_cell: Option<(i32, i32)> = None;
        for &(x, y, mask) in search.starts {
            let Some(index) = self.index(x, y) else {
                continue;
            };
            if is_goal[index] {
                shared_cell = Some(match shared_cell {
                    Some(best) if best < (x, y) => best,
                    _ => (x, y),
                });
            }
            start_mask[index] = mask;
            is_start[index] = true;
        }
        if let Some(cell) = shared_cell {
            return Some(vec![cell]);
        }
        let side = &self.layers[search.layer];
        let ground = search.layer == GROUND;
        let mut best = vec![f32::INFINITY; size * DIRS];
        let mut parent = vec![usize::MAX; size * DIRS];
        let mut open: BinaryHeap<Node> = BinaryHeap::new();
        let mut order: u32 = 0;
        for &(x, y, _) in search.starts {
            let Some(index) = self.index(x, y) else {
                continue;
            };
            best[index * DIRS + NO_DIR] = 0.0;
            open.push(Node {
                estimate: heuristic(x, y, gx0, gx1, gy0, gy1),
                order,
                index,
                direction: NO_DIR,
                crossing: false,
            });
            order += 1;
        }
        while let Some(node) = open.pop() {
            if node.estimate > search.limit {
                return None;
            }
            let state = node.index * DIRS + node.direction;
            let here = best[state];
            if node.direction != NO_DIR && !node.crossing && is_goal[node.index] {
                return Some(self.unwind(&parent, state));
            }
            let leaving = if node.direction == NO_DIR && is_start[node.index] {
                start_mask[node.index]
            } else {
                0
            };
            let (x, y) = self.cell(node.index);
            for step in 0..4 {
                if node.crossing && step != node.direction {
                    continue;
                }
                if leaving != 0 && leaving & (1 << step) == 0 {
                    continue;
                }
                if node.direction != NO_DIR && step == OPPOSITE[node.direction] {
                    continue;
                }
                let nx = x + STEPS[step].0;
                let ny = y + STEPS[step].1;
                let Some(next) = self.index(nx, ny) else {
                    continue;
                };
                if side.blocked[next] || (ground && self.pipe_unit(next)) {
                    continue;
                }
                let owners = side.reserved.get(&next);
                let foreign = owners.is_some_and(|list| !list.contains(&search.wire));
                let mut cost = 1.0 + self.history_cost * side.history[next];
                let mut crossing = false;
                if is_goal[next] {
                    let mask = goal_mask[next];
                    if mask != 0 && mask & (1 << step) == 0 {
                        continue;
                    }
                }
                if is_goal[next] && attach[next] {
                    if foreign {
                        continue;
                    }
                } else {
                    let (others, axis) = side.others(next, search.wire);
                    if foreign && !side.all_owned(next, search.wire, owners.unwrap()) {
                        continue;
                    }
                    // A splitter or converger is a building standing on the cell: nothing else
                    // may pass through it, whether or not a wire still holds the cell.
                    if side.unit[next] {
                        continue;
                    }
                    if others > 0 {
                        let wanted = if step % 2 == 0 { AXIS_H } else { AXIS_V };
                        let legal = others == 1 && axis == wanted;
                        if legal && (ground || self.ground_free(next)) {
                            cost += self.bridge_cost;
                            crossing = true;
                        } else if foreign || !search.share {
                            continue;
                        } else {
                            cost += search.present_cost * (1.0 + side.history[next]);
                        }
                    }
                }
                if node.direction != NO_DIR && step != node.direction {
                    cost += self.turn_cost;
                }
                let candidate = here + cost;
                let next_state = next * DIRS + step;
                if candidate < best[next_state] {
                    best[next_state] = candidate;
                    parent[next_state] = state;
                    open.push(Node {
                        estimate: candidate + heuristic(nx, ny, gx0, gx1, gy0, gy1),
                        order,
                        index: next,
                        direction: step,
                        crossing,
                    });
                    order += 1;
                }
            }
        }
        None
    }

    fn unwind(&self, parent: &[usize], state: usize) -> Vec<(i32, i32)> {
        let mut path = Vec::new();
        let mut current = state;
        loop {
            path.push(self.cell(current / DIRS));
            let up = parent[current];
            if up == usize::MAX {
                break;
            }
            current = up;
        }
        path.reverse();
        path
    }
}

/// Manhattan distance to the goals' bounding box: never an overestimate.
fn heuristic(x: i32, y: i32, gx0: i32, gx1: i32, gy0: i32, gy1: i32) -> f32 {
    let dx = if x < gx0 {
        gx0 - x
    } else if x > gx1 {
        x - gx1
    } else {
        0
    };
    let dy = if y < gy0 {
        gy0 - y
    } else if y > gy1 {
        y - gy1
    } else {
        0
    };
    (dx + dy) as f32
}
