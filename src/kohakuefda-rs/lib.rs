// PyO3 generates conversions clippy reads as redundant.
#![allow(clippy::useless_conversion)]

//! KohakuEFDA native routing grid and A*; Python owns planning, placement and verification.

use pyo3::prelude::*;

mod bindings;
pub mod route;

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("BACKEND_API", 1u32)?;
    bindings::register_route_types(m)?;
    Ok(())
}
