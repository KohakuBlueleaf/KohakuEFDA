// PyO3 generates conversions clippy reads as redundant.
#![allow(clippy::useless_conversion)]

//! KohakuEFDA native hot paths. Exports `_Grid`: the two-layer routing grid and its A*, the
//! search a layout run spends itself on. Python keeps every stage, rule and decision; Rust only
//! holds the occupancy and walks it. The proxy is `kohakuefda.route.pathfinder.RouteGrid`.

use pyo3::prelude::*;

mod route;

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    route::register_route_types(m)?;
    Ok(())
}
