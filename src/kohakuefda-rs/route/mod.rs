//! Solver-independent grid, occupancy and A* kernels.
//!
//! No solver policies or Python bindings live in this module. The binding adapter
//! in `bindings.rs` exports these mechanisms to the Python framework.

pub mod core;

#[cfg(test)]
mod tests;
