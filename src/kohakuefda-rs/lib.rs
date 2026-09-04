// PyO3 generates conversions clippy reads as redundant.
#![allow(clippy::useless_conversion)]

//! KohakuEFDA native hot paths. Exports `_Grid`, the two-layer routing grid and its A*, and
//! `_Placement`, the placement a heuristic search walks over with its incremental cost.
//! Python keeps every stage, rule and decision; Rust holds what a run spends itself on.

use pyo3::prelude::*;

mod heuristic;
mod route;

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    route::register_route_types(m)?;
    heuristic::register_heuristic_types(m)?;
    Ok(())
}
