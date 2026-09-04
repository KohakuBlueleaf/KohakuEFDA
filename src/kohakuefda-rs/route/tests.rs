//! Tests for the routing grid and its search.

use super::core::{Ends, Grid, Search, AXIS_H, AXIS_V, GROUND, SKY};

fn grid(width: usize, height: usize) -> Grid {
    Grid::new(width, height, 0.5, 4.0, 1.0)
}

fn ends(cells: &[(i32, i32)]) -> Ends {
    cells.iter().map(|&(x, y)| (x, y, 0u8)).collect()
}

fn search<'a>(starts: &'a Ends, goals: &'a Ends) -> Search<'a> {
    Search {
        layer: GROUND,
        wire: 1,
        starts,
        goals,
        present_cost: 2.0,
        share: false,
        limit: f32::INFINITY,
        shared: None,
    }
}

#[test]
fn a_straight_run_is_the_cells_between() {
    let board = grid(8, 8);
    let (starts, goals) = (ends(&[(1, 1)]), ends(&[(4, 1)]));
    let path = board.astar(&search(&starts, &goals)).unwrap();
    assert_eq!(path, vec![(1, 1), (2, 1), (3, 1), (4, 1)]);
}

#[test]
fn a_cell_that_is_both_end_is_the_whole_path() {
    let board = grid(8, 8);
    let (starts, goals) = (ends(&[(3, 3)]), ends(&[(3, 3)]));
    assert_eq!(board.astar(&search(&starts, &goals)).unwrap(), vec![(3, 3)]);
}

#[test]
fn blocked_cells_are_walked_around() {
    let mut board = grid(8, 8);
    for y in 0..7 {
        let index = board.index(2, y).unwrap();
        board.layers[GROUND].blocked[index] = true;
    }
    let (starts, goals) = (ends(&[(1, 1)]), ends(&[(4, 1)]));
    let path = board.astar(&search(&starts, &goals)).unwrap();
    assert!(path.contains(&(2, 7)));
    assert_eq!(path.first(), Some(&(1, 1)));
    assert_eq!(path.last(), Some(&(4, 1)));
}

#[test]
fn a_wall_with_no_way_round_has_no_path() {
    let mut board = grid(8, 8);
    for y in 0..8 {
        let index = board.index(2, y).unwrap();
        board.layers[GROUND].blocked[index] = true;
    }
    let (starts, goals) = (ends(&[(1, 1)]), ends(&[(4, 1)]));
    assert!(board.astar(&search(&starts, &goals)).is_none());
}

#[test]
fn a_perpendicular_wire_is_crossed_and_a_parallel_one_is_not() {
    let mut board = grid(8, 8);
    for y in 0..8 {
        let index = board.index(2, y).unwrap();
        board.hold(GROUND, index, 9, AXIS_V);
    }
    let (starts, goals) = (ends(&[(1, 1)]), ends(&[(4, 1)]));
    let path = board.astar(&search(&starts, &goals)).unwrap();
    assert_eq!(path, vec![(1, 1), (2, 1), (3, 1), (4, 1)]);

    let mut along = grid(8, 8);
    for y in 0..8 {
        let index = along.index(2, y).unwrap();
        along.hold(GROUND, index, 9, AXIS_H);
    }
    assert!(along.astar(&search(&starts, &goals)).is_none());
}

#[test]
fn a_unit_is_never_crossed() {
    let mut board = grid(8, 8);
    for y in 0..8 {
        let index = board.index(2, y).unwrap();
        board.hold(GROUND, index, 9, AXIS_V);
    }
    let (starts, goals) = (ends(&[(1, 1)]), ends(&[(4, 1)]));
    assert!(board.astar(&search(&starts, &goals)).is_some());
    for y in 0..8 {
        let index = board.index(2, y).unwrap();
        board.layers[GROUND].unit[index] = true;
    }
    assert!(board.astar(&search(&starts, &goals)).is_none());
}

#[test]
fn a_belt_will_not_pass_under_a_pipe_bridge() {
    let mut board = grid(8, 8);
    for y in 0..8 {
        let index = board.index(2, y).unwrap();
        board.layers[SKY].unit[index] = true;
    }
    let (starts, goals) = (ends(&[(1, 1)]), ends(&[(4, 1)]));
    assert!(board.astar(&search(&starts, &goals)).is_none());
}

#[test]
fn a_reserved_cell_is_closed_to_everyone_else() {
    let mut board = grid(8, 8);
    for y in 0..8 {
        let index = board.index(2, y).unwrap();
        board.layers[GROUND].reserved.insert(index, vec![7]);
    }
    let (starts, goals) = (ends(&[(1, 1)]), ends(&[(4, 1)]));
    assert!(board.astar(&search(&starts, &goals)).is_none());
    let mut mine = search(&starts, &goals);
    mine.wire = 7;
    assert!(board.astar(&mine).is_some());
}

#[test]
fn the_budget_stops_a_long_way_round() {
    let mut board = grid(20, 20);
    for y in 0..19 {
        let index = board.index(2, y).unwrap();
        board.layers[GROUND].blocked[index] = true;
    }
    let (starts, goals) = (ends(&[(1, 1)]), ends(&[(4, 1)]));
    let mut tight = search(&starts, &goals);
    tight.limit = 8.0;
    assert!(board.astar(&tight).is_none());
    let mut loose = search(&starts, &goals);
    loose.limit = 100.0;
    assert!(board.astar(&loose).is_some());
}

#[test]
fn a_start_may_be_told_which_way_to_leave() {
    let board = grid(8, 8);
    let goals = ends(&[(1, 4)]);
    let north_only: Ends = vec![(1, 1, 1 << 0)];
    let path = board.astar(&search(&north_only, &goals)).unwrap();
    assert_eq!(path[1], (1, 0));
    let south_only: Ends = vec![(1, 1, 1 << 2)];
    let path = board.astar(&search(&south_only, &goals)).unwrap();
    assert_eq!(path, vec![(1, 1), (1, 2), (1, 3), (1, 4)]);
}
