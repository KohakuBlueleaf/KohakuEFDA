//! The routing grid and its A*.
//!
//! `pathfinder.astar` is around 95% of a layout run and every inner step of it is a dict or set
//! lookup keyed by an `(x, y)` tuple. `core` keeps the same occupancy in flat arrays indexed by
//! `y * width + x`, so a step is an array read; `python` binds it as `_Grid`. The cost model is
//! the Python one cell for cell, and `tests/test_native.py` holds the two to the same paths.

pub mod core;
pub mod python;

pub use python::register_route_types;

#[cfg(test)]
mod tests;
