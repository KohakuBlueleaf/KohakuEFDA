//! The crate's own checks on the placement cost and the moves.

use crate::heuristic::core::{Placement, Scale, Terms, Weights};
use crate::heuristic::search::{anneal, Rng, Settings};

fn two_blocks() -> Placement {
    let size = vec![[(3, 3); 4], [(3, 3); 4]];
    let offset = vec![
        [vec![(0, 0)], vec![(0, 0)], vec![(0, 0)], vec![(0, 0)]],
        [vec![(0, 0)], vec![(0, 0)], vec![(0, 0)], vec![(0, 0)]],
    ];
    Placement {
        count: 2,
        x: vec![0, 10],
        y: vec![0, 0],
        rotation: vec![0, 0],
        w: vec![3, 3],
        h: vec![3, 3],
        size,
        offset,
        pad: vec![[(0, 0, 0, 0); 4], [(0, 0, 0, 0); 4]],
        margin: vec![0, 0],
        extra: vec![0, 0],
        frozen: vec![false, false],
        wire_from: vec![(0, 0)],
        wire_to: vec![(1, 0)],
        incident: vec![vec![0], vec![0]],
        length: vec![0],
        groups: vec![],
        group_of: vec![-1, -1],
        area_rect: (0, 0, 40, 40),
        heat: vec![0.0; 40 * 40],
        stride: 40,
        floor: 18,
        weights: Weights {
            area: 1.0,
            wire: 1.0,
            overlap: 8.0,
            group: 8.0,
            shut: 8.0,
            crowd: 1.0,
            tight: 4.0,
            slack: 1.5,
        },
        scale: Scale {
            area: 1.0,
            wire: 1.0,
        },
        terms: Terms::default(),
    }
}

#[test]
fn overlap_is_the_shared_area() {
    let mut state = two_blocks();
    state.recompute();
    assert_eq!(state.terms.overlap, 0);
    state.put(1, 1, 0, 0);
    assert_eq!(state.terms.overlap, 6);
}

#[test]
fn a_wire_costs_the_span_between_its_pins() {
    let mut state = two_blocks();
    state.recompute();
    assert_eq!(state.terms.wire, 10);
    state.put(1, 4, 3, 0);
    assert_eq!(state.terms.wire, 7);
}

#[test]
fn moving_keeps_the_cost_exact() {
    let mut state = two_blocks();
    state.recompute();
    let mut rng = Rng::new(9);
    for _ in 0..500 {
        let block = rng.below(2);
        let rotation = rng.below(4);
        let (x, y) = state.inside(
            block,
            rng.between(0, 36),
            rng.between(0, 36),
            rotation,
        );
        state.put(block, x, y, rotation);
        let running = state.terms;
        state.recompute();
        assert_eq!(running, state.terms);
    }
}

#[test]
fn a_block_never_leaves_its_room() {
    let state = two_blocks();
    let (x, y) = state.inside(0, 100, -100, 0);
    assert_eq!((x, y), (37, 0));
}

#[test]
fn annealing_pulls_two_blocks_together() {
    let mut state = two_blocks();
    state.x = vec![0, 30];
    state.y = vec![0, 30];
    state.recompute();
    let before = state.terms.wire;
    let settings = Settings {
        moves: 4000,
        window: 100,
        warmup: 50,
        accept_initial: 0.9,
        end: 0.0001,
        range_start: 0.5,
        range_floor: 1,
        weights: [6.0, 3.0, 2.0, 1.0],
        polish: 500,
        polish_overlap: 128.0,
    };
    anneal(&mut state, &settings, 5);
    state.recompute();
    assert!(state.terms.wire < before);
    assert_eq!(state.terms.overlap, 0);
}
