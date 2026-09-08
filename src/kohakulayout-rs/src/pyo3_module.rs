//! The Python surface: IR functions on JSON strings, and the kernel as a handle.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::BTreeSet;

use crate::kernel::grid::Grid;
use crate::text;

fn err<E: std::fmt::Display>(e: E) -> PyErr {
    PyValueError::new_err(e.to_string())
}

/// The levels held by a `.kl` text as one JSON document: `version`, `physics`, `params`, `fabric`, `netlist`, `layout`, `assessment`.
#[pyfunction]
#[pyo3(signature = (text_in, context=None))]
fn parse_kl(text_in: &str, context: Option<&str>) -> PyResult<String> {
    text::parse_to_json(text_in, context).map_err(err)
}

/// Canonical text of a level given as its content JSON; a layout reads pin endpoints from `context` (a problem or netlist).
#[pyfunction]
#[pyo3(signature = (level_json, context=None))]
fn write_kl(level_json: &str, context: Option<&str>) -> PyResult<String> {
    text::write_from_json(level_json, context).map_err(err)
}

/// The flat form of a netlist or problem given as content JSON.
#[pyfunction]
fn flatten(level_json: &str) -> PyResult<String> {
    crate::text::levels::flatten_json(level_json).map_err(err)
}

/// The canonical JSON string a level's digest is computed on.
#[pyfunction]
fn canonical(level_json: &str) -> PyResult<String> {
    crate::text::levels::canonical_json(level_json).map_err(err)
}

/// The digest of a level given as content JSON.
#[pyfunction]
fn digest(level_json: &str) -> PyResult<String> {
    crate::text::levels::digest_json(level_json).map_err(err)
}

#[pyclass(name = "Grid")]
struct PyGrid {
    inner: Grid,
}

#[pymethods]
impl PyGrid {
    #[new]
    fn new(width: i64, height: i64, layers: Vec<String>) -> PyGrid {
        PyGrid { inner: Grid::new(width, height, layers) }
    }

    #[getter]
    fn width(&self) -> i64 {
        self.inner.width
    }

    #[getter]
    fn height(&self) -> i64 {
        self.inner.height
    }

    #[getter]
    fn layers(&self) -> Vec<String> {
        self.inner.layers.clone()
    }

    fn occupy(&mut self, layer: &str, cells: Vec<(i64, i64)>, holder: &str) {
        self.inner.occupy(layer, &cells, holder);
    }

    fn free(&mut self, layer: &str, cells: Vec<(i64, i64)>, holder: &str) {
        self.inner.free(layer, &cells, holder);
    }

    fn clear(&mut self) {
        self.inner.clear();
    }

    fn holders_at(&self, layer: &str, xy: (i64, i64)) -> Vec<String> {
        self.inner.holders_at(layer, xy)
    }

    fn holders(&self, layer: &str, cells: Vec<(i64, i64)>) -> Vec<Vec<String>> {
        self.inner.holders(layer, &cells)
    }

    fn free_for(&self, layer: &str, cells: Vec<(i64, i64)>) -> bool {
        self.inner.free_for(layer, &cells)
    }

    fn cells_of(&self, holder: &str) -> std::collections::BTreeMap<String, Vec<(i64, i64)>> {
        self.inner.cells_of(holder)
    }

    fn holders_on(&self, layer: &str) -> Vec<String> {
        self.inner.holders_on(layer)
    }

    fn holders_map(&self, layer: &str) -> Vec<((i64, i64), Vec<String>)> {
        self.inner.holders_map(layer)
    }

    #[pyo3(signature = (layer=None, mask=None))]
    fn extent(
        &self,
        layer: Option<&str>,
        mask: Option<Vec<(i64, i64)>>,
    ) -> Option<(i64, i64, i64, i64)> {
        let set: Option<BTreeSet<(i64, i64)>> = mask.map(|m| m.into_iter().collect());
        self.inner.extent(layer, set.as_ref())
    }

    fn occupancy(&self, layer: &str) -> Vec<u8> {
        self.inner.occupancy(layer)
    }

    fn save(&self) -> Vec<u8> {
        self.inner.save().into_bytes()
    }

    fn load(&mut self, blob: Vec<u8>) -> PyResult<()> {
        let text = String::from_utf8(blob).map_err(err)?;
        self.inner.load(&text).map_err(err)
    }
}

#[pymodule]
fn kohakulayout_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_kl, m)?)?;
    m.add_function(wrap_pyfunction!(write_kl, m)?)?;
    m.add_function(wrap_pyfunction!(flatten, m)?)?;
    m.add_function(wrap_pyfunction!(canonical, m)?)?;
    m.add_function(wrap_pyfunction!(digest, m)?)?;
    m.add_class::<PyGrid>()?;
    Ok(())
}
