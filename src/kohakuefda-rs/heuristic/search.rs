//! Moves over a placement and the annealing that uses them: VPR's set plus a macro shift,
//! with undo as another move so nothing is copied.

use crate::heuristic::core::Placement;

/// A small deterministic generator, so a run is a pure function of its seed and the crate
/// keeps to one dependency.
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: u64) -> Self {
        Rng(seed ^ 0x9e3779b97f4a7c15)
    }

    pub fn next(&mut self) -> u64 {
        let mut x = self.0.wrapping_add(0x9e3779b97f4a7c15);
        self.0 = x;
        x = (x ^ (x >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        x = (x ^ (x >> 27)).wrapping_mul(0x94d049bb133111eb);
        x ^ (x >> 31)
    }

    pub fn below(&mut self, bound: usize) -> usize {
        if bound == 0 {
            0
        } else {
            (self.next() % bound as u64) as usize
        }
    }

    pub fn between(&mut self, low: i32, high: i32) -> i32 {
        if high <= low {
            return low;
        }
        low + (self.next() % ((high - low + 1) as u64)) as i32
    }

    pub fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
}

/// What a proposal touched and where those blocks stood before it.
pub struct Move {
    pub blocks: Vec<usize>,
    pub before: Vec<(i32, i32, usize)>,
}

pub struct Moves {
    pub movable: Vec<usize>,
    pub weights: [f64; 4],
    pub span: i32,
    pub range: i32,
    pub floor: i32,
}

impl Moves {
    pub fn new(state: &Placement, weights: [f64; 4], start: f64, floor: i32) -> Self {
        let (x0, y0, x1, y1) = state.area_rect;
        let span = (x1 - x0).max(y1 - y0);
        Moves {
            movable: (0..state.count).filter(|&b| !state.frozen[b]).collect(),
            weights,
            span,
            range: ((span as f64 * start) as i32).max(1),
            floor: floor.max(1),
        }
    }

    pub fn narrow(&mut self, fraction: f64) {
        self.range = ((self.span as f64 * fraction) as i32).max(self.floor);
    }

    fn record(&self, state: &Placement, blocks: Vec<usize>) -> Move {
        let before = blocks
            .iter()
            .map(|&b| (state.x[b], state.y[b], state.rotation[b]))
            .collect();
        Move { blocks, before }
    }

    pub fn propose(&self, state: &mut Placement, rng: &mut Rng) -> Option<Move> {
        if self.movable.is_empty() {
            return None;
        }
        let total: f64 = self.weights.iter().sum();
        let mut pick = rng.unit() * total;
        let mut kind = 0;
        for (index, weight) in self.weights.iter().enumerate() {
            if pick < *weight {
                kind = index;
                break;
            }
            pick -= weight;
        }
        if kind == 1 && self.movable.len() < 2 {
            kind = 0;
        }
        Some(match kind {
            1 => self.swap(state, rng),
            2 => self.rotate(state, rng),
            3 => self.shift(state, rng),
            _ => self.displace(state, rng),
        })
    }

    fn displace(&self, state: &mut Placement, rng: &mut Rng) -> Move {
        let block = self.movable[rng.below(self.movable.len())];
        let move_ = self.record(state, vec![block]);
        let rotation = state.rotation[block];
        let (x, y) = state.inside(
            block,
            state.x[block] + rng.between(-self.range, self.range),
            state.y[block] + rng.between(-self.range, self.range),
            rotation,
        );
        state.put(block, x, y, rotation);
        move_
    }

    fn swap(&self, state: &mut Placement, rng: &mut Rng) -> Move {
        let first = self.movable[rng.below(self.movable.len())];
        let mut second = first;
        while second == first {
            second = self.movable[rng.below(self.movable.len())];
        }
        let move_ = self.record(state, vec![first, second]);
        let target = (state.x[second], state.y[second]);
        let source = (state.x[first], state.y[first]);
        state.put(first, target.0, target.1, state.rotation[first]);
        state.put(second, source.0, source.1, state.rotation[second]);
        move_
    }

    fn rotate(&self, state: &mut Placement, rng: &mut Rng) -> Move {
        let block = self.movable[rng.below(self.movable.len())];
        let move_ = self.record(state, vec![block]);
        let turned = (state.rotation[block] + 1 + rng.below(3)) % 4;
        let (x, y) = state.inside(block, state.x[block], state.y[block], turned);
        state.put(block, x, y, turned);
        move_
    }

    fn shift(&self, state: &mut Placement, rng: &mut Rng) -> Move {
        let down = rng.unit() < 0.5;
        let pivot = self.movable[rng.below(self.movable.len())];
        let line = if down { state.y[pivot] } else { state.x[pivot] };
        let step = if rng.unit() < 0.5 { -1 } else { 1 };
        let blocks: Vec<usize> = self
            .movable
            .iter()
            .copied()
            .filter(|&b| if down { state.y[b] } else { state.x[b] } >= line)
            .collect();
        let move_ = self.record(state, blocks.clone());
        for block in blocks {
            let rotation = state.rotation[block];
            let (x, y) = state.inside(
                block,
                state.x[block] + if down { 0 } else { step },
                state.y[block] + if down { step } else { 0 },
                rotation,
            );
            state.put(block, x, y, rotation);
        }
        move_
    }

    pub fn undo(&self, state: &mut Placement, move_: &Move) {
        for (slot, &block) in move_.blocks.iter().enumerate().rev() {
            let (x, y, rotation) = move_.before[slot];
            state.put(block, x, y, rotation);
        }
    }
}

pub struct Trace {
    pub steps: usize,
    pub accepted: usize,
    pub best: f64,
}

/// The temperature at which the average uphill move is taken with probability `accept`.
fn first_temperature(uphill: &[f64], accept: f64) -> f64 {
    if uphill.is_empty() {
        return 1.0;
    }
    let average = uphill.iter().sum::<f64>() / uphill.len() as f64;
    let chance = accept.clamp(1e-6, 0.999);
    (average / -chance.ln()).max(1e-6)
}

/// Called every `watch_every` moves with the step, the temperature, the running cost and where
/// every block stands, so a watcher can draw the walk without it leaving the native side.
pub type Watcher<'a> = &'a mut dyn FnMut(usize, f64, f64, Vec<(i32, i32, usize)>);

pub struct Settings {
    pub watch_every: usize,
    pub moves: usize,
    pub window: usize,
    pub warmup: usize,
    pub accept_initial: f64,
    pub end: f64,
    pub range_start: f64,
    pub range_floor: i32,
    pub weights: [f64; 4],
    pub polish: usize,
    pub polish_overlap: f64,
}

/// Anneal a placement in place and leave it at the best arrangement seen.
pub fn anneal(
    state: &mut Placement,
    settings: &Settings,
    seed: u64,
    mut watch: Option<Watcher>,
) -> Trace {
    let mut rng = Rng::new(seed);
    let mut moves = Moves::new(state, settings.weights, settings.range_start, settings.range_floor);
    state.rescale();
    let mut uphill = Vec::new();
    for _ in 0..settings.warmup {
        let before = state.cost();
        match moves.propose(state, &mut rng) {
            Some(move_) => {
                let delta = state.cost() - before;
                if delta > 0.0 {
                    uphill.push(delta);
                }
                moves.undo(state, &move_);
            }
            None => break,
        }
    }
    let first = first_temperature(&uphill, settings.accept_initial);
    let mut temperature = first;
    let mut current = state.cost();
    let mut best = current;
    let mut kept: Vec<(i32, i32, usize)> = (0..state.count)
        .map(|b| (state.x[b], state.y[b], state.rotation[b]))
        .collect();
    let mut taken = 0;
    for step in 0..settings.moves {
        let move_ = match moves.propose(state, &mut rng) {
            Some(move_) => move_,
            None => break,
        };
        let after = state.cost();
        let delta = after - current;
        if delta <= 0.0 || rng.unit() < (-delta / temperature.max(1e-9)).exp() {
            current = after;
            taken += 1;
            if after < best - 1e-9 {
                best = after;
                for block in 0..state.count {
                    kept[block] = (state.x[block], state.y[block], state.rotation[block]);
                }
            }
        } else {
            moves.undo(state, &move_);
        }
        if step % settings.window == 0 && step > 0 {
            let share = step as f64 / settings.moves as f64;
            temperature = first * settings.end.powf(share);
            moves.narrow(temperature / first.max(1e-9));
        }
        if let Some(draw) = watch.as_deref_mut() {
            if settings.watch_every > 0 && step % settings.watch_every == 0 {
                let anchors = (0..state.count)
                    .map(|b| (state.x[b], state.y[b], state.rotation[b]))
                    .collect();
                draw(step, temperature, current, anchors);
            }
        }
    }
    for block in 0..state.count {
        let (x, y, rotation) = kept[block];
        state.put(block, x, y, rotation);
    }
    polish(state, &mut moves, &mut rng, settings);
    Trace { steps: settings.moves, accepted: taken, best }
}

/// Harden the answer: overlap and corridors priced far higher, only improvements taken.
fn polish(state: &mut Placement, moves: &mut Moves, rng: &mut Rng, settings: &Settings) {
    if settings.polish == 0 {
        return;
    }
    let soft = state.weights;
    state.weights.overlap = settings.polish_overlap;
    state.weights.shut = settings.polish_overlap;
    moves.narrow(0.0);
    let mut current = state.cost();
    for _ in 0..settings.polish {
        match moves.propose(state, rng) {
            Some(move_) => {
                let after = state.cost();
                if after < current {
                    current = after;
                } else {
                    moves.undo(state, &move_);
                }
            }
            None => break,
        }
    }
    separate(state, &moves.movable.clone());
    state.weights = soft;
    state.recompute();
}

/// Push overlapping blocks apart until none are left, whatever else it costs. Either block of a
/// pair will do, and a pair with no way out is set aside rather than ending the pass.
fn separate(state: &mut Placement, movable: &[usize]) {
    let mut stuck: Vec<(usize, usize)> = Vec::new();
    for _ in 0..state.count * 16 {
        if state.terms.overlap == 0 && state.terms.shut == 0 {
            return;
        }
        match collision(state, movable, &stuck) {
            None => return,
            Some((block, other)) => {
                if push(state, block, other) || push(state, other, block) {
                    stuck.clear();
                } else {
                    stuck.push((block, other));
                }
            }
        }
    }
}

/// Move one block clear of another; false when no direction helps.
fn push(state: &mut Placement, block: usize, other: usize) -> bool {
    if state.frozen[block] {
        return false;
    }
    let (ax0, ay0, ax1, ay1) = state.rect(block);
    let (bx0, by0, bx1, by1) = state.rect(other);
    let home = (state.x[block], state.y[block]);
    let rotation = state.rotation[block];
    let mut best = state.terms.overlap;
    let mut landing = None;
    for (dx, dy) in [
        (bx1 - ax0, 0),
        (bx0 - ax1, 0),
        (0, by1 - ay0),
        (0, by0 - ay1),
    ] {
        let (x, y) = state.inside(block, home.0 + dx, home.1 + dy, rotation);
        state.put(block, x, y, rotation);
        if state.terms.overlap < best {
            best = state.terms.overlap;
            landing = Some((x, y));
        }
        state.put(block, home.0, home.1, rotation);
    }
    match landing {
        None => false,
        Some((x, y)) => {
            state.put(block, x, y, rotation);
            true
        }
    }
}

fn collision(
    state: &Placement,
    movable: &[usize],
    skip: &[(usize, usize)],
) -> Option<(usize, usize)> {
    for &block in movable {
        for other in 0..state.count {
            if other == block || skip.contains(&(block, other)) {
                continue;
            }
            if state.overlap(block, other) > 0 || state.shut_pair(block, other) > 0 {
                return Some((block, other));
            }
        }
    }
    None
}
