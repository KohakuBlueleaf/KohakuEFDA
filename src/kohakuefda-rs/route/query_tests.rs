//! Ordered query behavior over the native occupancy representation.

use super::core::{Grid, AXIS_H, AXIS_V};

#[test]
fn clipped_bounds_exclude_fixed_terrain_and_external_routes() {
    let mut grid = Grid::new(10, 10, 0.5, 4.0, 1.0);
    grid.layers[0].blocked[0] = true;
    assert_eq!(grid.extent_in((-20, -20, 30, 30)), None);
    let inside = grid.index(4, 3).unwrap();
    let outside = grid.index(8, 8).unwrap();
    grid.layers[0].owned[inside] = true;
    grid.hold(1, outside, 1, AXIS_H);
    assert_eq!(grid.extent_in((2, 2, 6, 6)), Some((4, 3, 5, 4)));
    assert_eq!(grid.extent_in((0, 0, 0, 0)), None);
}

#[test]
fn ordered_junctions_exclude_units_crossings_and_ground_occupancy() {
    let mut grid = Grid::new(10, 10, 0.5, 4.0, 1.0);
    let chain = vec![(1, 3), (2, 3), (3, 3), (4, 3), (5, 3)];
    for x in 2..5 {
        grid.hold(1, grid.index(x, 3).unwrap(), 1, AXIS_H);
    }
    let chains = vec![chain.clone(), chain.into_iter().rev().collect()];
    assert_eq!(
        grid.straight_cells(1, &chains, (0, 0, 10, 10)),
        vec![
            (2, 3, 1),
            (3, 3, 1),
            (4, 3, 1),
            (4, 3, 3),
            (3, 3, 3),
            (2, 3, 3)
        ]
    );
    let unit = grid.index(2, 3).unwrap();
    grid.layers[1].unit[unit] = true;
    grid.hold(1, grid.index(3, 3).unwrap(), 2, AXIS_V);
    grid.hold(0, grid.index(4, 3).unwrap(), 3, AXIS_H);
    assert!(grid.straight_cells(1, &chains, (0, 0, 10, 10)).is_empty());
}

#[test]
fn outside_bridge_query_checks_occupancy_not_just_the_boundary() {
    let mut grid = Grid::new(10, 10, 0.5, 4.0, 1.0);
    let area = (3, 3, 8, 8);
    assert!(!grid.bridges_outside(1, &[(2, 3)], area));
    grid.hold(1, grid.index(2, 3).unwrap(), 1, AXIS_H);
    assert!(grid.bridges_outside(1, &[(2, 3)], area));
    assert!(!grid.bridges_outside(0, &[(2, 3)], area));
    assert!(!grid.bridges_outside(1, &[(-1, -1)], area));
}
