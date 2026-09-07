//! Solver-independent grid, occupancy and A* kernels.
//!
//! No solver policies or Python bindings live in this module. The binding adapter
//! in `bindings.rs` exports these mechanisms to the Python framework.

pub mod core;
pub mod queries;

#[cfg(test)]
mod query_tests;
#[cfg(test)]
mod tests;
