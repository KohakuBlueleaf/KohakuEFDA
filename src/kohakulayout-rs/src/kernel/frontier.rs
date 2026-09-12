//! The open states of one search: a heap by key and queued order, or buckets by exact integer key
//! when the search's costs make every key an exact integer, which pop in the heap's order.

use std::cmp::Ordering;
use std::collections::BinaryHeap;

use super::classify::Query;

/// The first key the buckets do not hold; a search reaching it runs again on the heap.
const BUCKET_CAP: u64 = 1 << 20;

/// A queued state; the heap pops the least key, then the earliest queued.
#[derive(PartialEq, Eq)]
pub(super) struct Node {
    key: u64,
    order: u32,
    state: u32,
}

impl Ord for Node {
    fn cmp(&self, other: &Self) -> Ordering {
        other
            .key
            .cmp(&self.key)
            .then_with(|| other.order.cmp(&self.order))
    }
}

impl PartialOrd for Node {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// The open states of a search, popped by least key and then first queued.
pub(super) trait Frontier {
    /// Queue a state; false when the key lies past what the frontier holds.
    fn push(&mut self, key: u64, order: u32, state: u32) -> bool;
    fn pop(&mut self) -> Option<(u64, u32)>;
}

impl Frontier for BinaryHeap<Node> {
    fn push(&mut self, key: u64, order: u32, state: u32) -> bool {
        BinaryHeap::push(self, Node { key, order, state });
        true
    }

    fn pop(&mut self) -> Option<(u64, u32)> {
        BinaryHeap::pop(self).map(|n| (n.key, n.state))
    }
}

/// States queued by integer key, first in first out per key: the heap's order for exact keys.
#[derive(Default)]
pub(super) struct Buckets {
    lists: Vec<Vec<u32>>,
    heads: Vec<usize>,
    used: Vec<usize>,
    min: usize,
    len: usize,
}

impl Buckets {
    pub(super) fn clear(&mut self) {
        for &k in &self.used {
            self.lists[k].clear();
            self.heads[k] = 0;
        }
        self.used.clear();
        self.min = usize::MAX;
        self.len = 0;
    }
}

impl Frontier for Buckets {
    fn push(&mut self, key: u64, _order: u32, state: u32) -> bool {
        if key >= BUCKET_CAP {
            return false;
        }
        let k = key as usize;
        if k >= self.lists.len() {
            self.lists.resize_with(k + 1, Vec::new);
            self.heads.resize(k + 1, 0);
        }
        if self.lists[k].is_empty() {
            self.used.push(k);
        }
        self.lists[k].push(state);
        self.len += 1;
        self.min = self.min.min(k);
        true
    }

    fn pop(&mut self) -> Option<(u64, u32)> {
        if self.len == 0 {
            return None;
        }
        loop {
            let k = self.min;
            if self.heads[k] < self.lists[k].len() {
                let state = self.lists[k][self.heads[k]];
                self.heads[k] += 1;
                self.len -= 1;
                return Some((k as u64, state));
            }
            self.min += 1;
        }
    }
}

/// How estimates become keys: float bits or integers on the heap, integer units in buckets.
#[derive(Clone, Copy)]
pub(super) enum Keys {
    Heap,
    Buckets(i64),
}

fn gcd(a: i64, b: i64) -> i64 {
    if b == 0 {
        a
    } else {
        gcd(b, a % b)
    }
}

/// The bucket unit when every key is an exact integer multiple of it; None otherwise.
pub(super) fn bucket_unit(query: &Query) -> Option<i64> {
    let parts = [
        query.step,
        query.turn,
        query.crossing,
        query.share,
        query.corridor,
        query.ripup,
        query.displace,
    ];
    if parts.iter().any(|a| *a < 0) {
        return None;
    }
    let scale = query.float_scale;
    if scale > 0
        && parts
            .iter()
            .any(|a| *a != 0 && !((scale / gcd(*a, scale)) as u64).is_power_of_two())
    {
        return None;
    }
    Some(parts.iter().fold(0, |g, a| gcd(g, *a)).max(1))
}

impl Keys {
    pub(super) fn key(self, estimate: i64, float: Option<f32>, scale: i64) -> u64 {
        match (self, float) {
            (Keys::Heap, Some(f)) => f.to_bits() as u64,
            (Keys::Heap, None) => estimate as u64,
            (Keys::Buckets(unit), Some(f)) => (f as f64 * scale as f64 / unit as f64) as u64,
            (Keys::Buckets(unit), None) => (estimate / unit) as u64,
        }
    }

    /// The estimate a key stands for: the float under a float scale, else the integer.
    pub(super) fn estimate(self, key: u64, floats: bool, scale: i64) -> (i64, f32) {
        match (self, floats) {
            (Keys::Heap, true) => (0, f32::from_bits(key as u32)),
            (Keys::Heap, false) => (key as i64, 0.0),
            (Keys::Buckets(unit), true) => (0, (key as i64 * unit) as f32 / scale as f32),
            (Keys::Buckets(unit), false) => (key as i64 * unit, 0.0),
        }
    }
}
