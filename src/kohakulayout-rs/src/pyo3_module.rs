//! The Python surface: IR functions on JSON strings, and the kernel as a handle.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::{BTreeSet, HashMap};
use std::sync::{Arc, Mutex};

use crate::kernel::astar::{Classified, Prepared};

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

/// The layer classified for one rules text at one grid generation.
type ClassifiedCache = Option<(String, String, u64, Arc<Classified>)>;

#[pyclass(name = "Grid")]
struct PyGrid {
    inner: Grid,
    rules: Mutex<Option<(String, Arc<Prepared>)>>,
    classified: Mutex<ClassifiedCache>,
    walls: Mutex<HashMap<String, Vec<(i64, i64)>>>,
}

#[pymethods]
impl PyGrid {
    #[new]
    fn new(width: i64, height: i64, layers: Vec<String>) -> PyGrid {
        PyGrid {
            inner: Grid::new(width, height, layers),
            rules: Mutex::new(None),
            classified: Mutex::new(None),
            walls: Mutex::new(HashMap::new()),
        }
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

    /// A* from any source to any target under the rules JSON; the found path as JSON, or None.
    fn has_walls(&self, key: &str) -> PyResult<bool> {
        Ok(self
            .walls
            .lock()
            .map_err(|_| PyValueError::new_err("walls cache poisoned"))?
            .contains_key(key))
    }

    fn set_walls(&self, key: &str, cells: Vec<(i64, i64)>) -> PyResult<()> {
        self.walls
            .lock()
            .map_err(|_| PyValueError::new_err("walls cache poisoned"))?
            .insert(key.to_string(), cells);
        Ok(())
    }

    #[pyo3(signature = (layer, sources, targets, rules, avoid, own=Vec::new()))]
    fn astar(
        &self,
        layer: &str,
        sources: Vec<(i64, i64)>,
        targets: Vec<(i64, i64)>,
        rules: &str,
        avoid: Vec<(i64, i64)>,
        own: Vec<(i64, i64, u8)>,
    ) -> PyResult<Option<String>> {
        let prepared = {
            let mut cache = self
                .rules
                .lock()
                .map_err(|_| PyValueError::new_err("rules cache poisoned"))?;
            match cache.as_ref() {
                Some((text, prepared)) if text == rules => prepared.clone(),
                _ => {
                    let parsed: crate::kernel::astar::Rules =
                        serde_json::from_str(rules).map_err(err)?;
                    let registered = self
                        .walls
                        .lock()
                        .map_err(|_| PyValueError::new_err("walls cache poisoned"))?
                        .get(&parsed.walls_key)
                        .cloned()
                        .unwrap_or_default();
                    let prepared = Arc::new(Prepared::new(
                        parsed,
                        self.inner.width,
                        self.inner.height,
                        &registered,
                    ));
                    *cache = Some((rules.to_string(), prepared.clone()));
                    prepared
                }
            }
        };
        let classified = {
            let mut cache = self
                .classified
                .lock()
                .map_err(|_| PyValueError::new_err("classification cache poisoned"))?;
            let generation = self.inner.generation;
            match cache.as_ref() {
                Some((text, cached_layer, cached_generation, cells))
                    if text == rules
                        && cached_layer == layer
                        && *cached_generation == generation =>
                {
                    cells.clone()
                }
                _ => {
                    let cells =
                        Arc::new(crate::kernel::astar::classify(&self.inner, layer, &prepared));
                    *cache =
                        Some((rules.to_string(), layer.to_string(), generation, cells.clone()));
                    cells
                }
            }
        };
        Ok(crate::kernel::astar::find(
            &self.inner,
            &sources,
            &targets,
            &avoid,
            &own,
            &prepared,
            &classified,
        )
        .map(|f| serde_json::to_string(&f).unwrap()))
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
