//! The Python surface: IR functions on JSON strings, and the kernel as a handle.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::BTreeSet;
use std::sync::{Arc, Mutex};

use crate::kernel::astar::{Ask, Query, Scratch, View};
use crate::kernel::grid::Grid;
use crate::kernel::hash::Map;
use crate::kernel::judge::Regions;
use crate::kernel::layers::Layers;
use crate::kernel::records::{Records, Statics};
use crate::kernel::route::{Kit, Pass};
use crate::kernel::tables::{CarrierView, Tables};
use crate::text;

fn poisoned<T>(_: T) -> PyErr {
    PyValueError::new_err("a cache poisoned")
}

fn err<E: std::fmt::Display>(e: E) -> PyErr {
    PyValueError::new_err(e.to_string())
}

/// The levels of a `.kl` text as one JSON document.
#[pyfunction]
#[pyo3(signature = (text_in, context=None))]
fn parse_kl(text_in: &str, context: Option<&str>) -> PyResult<String> {
    text::parse_to_json(text_in, context).map_err(err)
}

/// Canonical text of a level's content JSON; a layout reads pin endpoints from `context`.
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
    tables: Mutex<Tables>,
    views: Mutex<Map<(String, u64), Arc<CarrierView>>>,
    layers: Mutex<Layers>,
    walls: Mutex<Map<String, Arc<Vec<bool>>>>,
    scratch: Mutex<Scratch>,
    regions: Mutex<Regions>,
    records: Mutex<Records>,
}

#[pymethods]
impl PyGrid {
    #[new]
    fn new(width: i64, height: i64, layers: Vec<String>) -> PyGrid {
        PyGrid {
            inner: Grid::new(width, height, layers),
            tables: Mutex::new(Tables::default()),
            views: Mutex::new(Map::default()),
            layers: Mutex::new(Layers::default()),
            walls: Mutex::new(Map::default()),
            scratch: Mutex::new(Scratch::default()),
            regions: Mutex::new(Regions::default()),
            records: Mutex::new(Records::default()),
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
        self.touch(layer, &cells);
    }

    fn free(&mut self, layer: &str, cells: Vec<(i64, i64)>, holder: &str) {
        self.inner.free(layer, &cells, holder);
        self.touch(layer, &cells);
    }

    fn set_runs(&mut self, layer: &str, holder: &str, runs: Vec<(i64, i64, u8)>) {
        let runs: Vec<((i64, i64), u8)> = runs.into_iter().map(|(x, y, m)| ((x, y), m)).collect();
        self.inner.set_runs(layer, holder, &runs);
        let cells: Vec<(i64, i64)> = runs.iter().map(|(xy, _)| *xy).collect();
        self.touch(layer, &cells);
    }

    fn run_at(&self, layer: &str, holder: &str, xy: (i64, i64)) -> u8 {
        self.inner.run_at(layer, holder, xy)
    }

    fn clear(&mut self) {
        self.inner.clear();
        self.reset();
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
        self.inner.load(&text).map_err(err)?;
        self.reset();
        Ok(())
    }

    fn has_walls(&self, key: &str) -> PyResult<bool> {
        Ok(self
            .walls
            .lock()
            .map_err(|_| PyValueError::new_err("walls cache poisoned"))?
            .contains_key(key))
    }

    /// The cells closed under a key, kept as a grid every search over the key shares.
    fn set_walls(&self, key: &str, cells: Vec<(i64, i64)>) -> PyResult<()> {
        let (w, h) = (self.inner.width.max(0) as usize, self.inner.height.max(0) as usize);
        let mut grid = vec![false; w * h];
        for (x, y) in cells {
            if x >= 0 && y >= 0 && (x as usize) < w && (y as usize) < h {
                grid[y as usize * w + x as usize] = true;
            }
        }
        self.walls
            .lock()
            .map_err(|_| PyValueError::new_err("walls cache poisoned"))?
            .insert(key.to_string(), Arc::new(grid));
        Ok(())
    }

    /// Every net with its carrier, replacing what was registered.
    fn set_nets(&self, nets: Vec<(String, String)>) -> PyResult<()> {
        self.lock_tables()?.set_nets(nets);
        self.layers
            .lock()
            .map_err(|_| PyValueError::new_err("layers cache poisoned"))?
            .reset();
        Ok(())
    }

    /// Per searching carrier, per other carrier: `{"share", "mode", "unit", "bent"}` as JSON.
    fn set_pairs(&self, json: &str) -> PyResult<()> {
        self.lock_tables()?.set_pairs(json).map_err(err)
    }

    /// Every crossing unit's `{"width", "height", "layers"}` as JSON, by footprint id.
    fn set_shapes(&self, json: &str) -> PyResult<()> {
        self.lock_tables()?.set_shapes(json).map_err(err)
    }

    /// A unit's facts a search reads: its footprint, owning net and whether it is a field emitter.
    fn note_unit(&self, id: &str, footprint: &str, owner: &str, field: bool) -> PyResult<()> {
        self.lock_tables()?.note_unit(id, footprint, owner, field);
        self.touch_holder(&format!("unit:{id}"))
    }

    fn set_reservation(&self, tag: &str, carrier: &str) -> PyResult<()> {
        self.lock_tables()?.set_reservation(tag, carrier);
        self.touch_holder(&format!("reserve:{tag}"))
    }

    /// A* under the query JSON: (cells, cost, crossings, rips, displaces), or None.
    #[pyo3(signature = (layer, sources, targets, rules, avoid, own=Vec::new()))]
    #[allow(clippy::type_complexity)]
    fn astar(
        &self,
        layer: &str,
        sources: Vec<(i64, i64)>,
        targets: Vec<(i64, i64)>,
        rules: &str,
        avoid: Vec<(i64, i64)>,
        own: Vec<(i64, i64, u8)>,
    ) -> PyResult<
        Option<(Vec<(i64, i64)>, i64, Vec<((i64, i64), String, bool)>, Vec<String>, Vec<String>)>,
    > {
        self.with_search(layer, rules, |ask, scratch, _| {
            crate::kernel::astar::find(&self.inner, &sources, &targets, &avoid, &own, ask, scratch)
                .map(|f| (f.cells, f.cost, f.crossings, f.rips, f.displaces))
        })
    }

    /// Every region's cells and the regions each unit footprint may stand in.
    fn set_regions(
        &self,
        regions: Vec<(String, Vec<(i64, i64)>)>,
        allowed: Vec<(String, Vec<String>)>,
    ) -> PyResult<()> {
        self.regions
            .lock()
            .map_err(|_| PyValueError::new_err("regions poisoned"))?
            .register(&regions, &allowed);
        Ok(())
    }

    /// A world's fixed records for the native routing pass, replacing whatever was mirrored before.
    fn register_records(&self, statics: &str) -> PyResult<()> {
        let statics: Statics = serde_json::from_str(statics).map_err(err)?;
        self.records
            .lock()
            .map_err(|_| PyValueError::new_err("records poisoned"))?
            .register(statics);
        Ok(())
    }

    /// Whether a world's records were registered on this grid.
    fn has_records(&self) -> PyResult<bool> {
        Ok(self
            .records
            .lock()
            .map_err(|_| PyValueError::new_err("records poisoned"))?
            .ready)
    }

    /// One native routing pass after the sync, every write undone: the answer as JSON.
    fn route_pass(&mut self, doc: &str) -> PyResult<Option<String>> {
        let Ok(mut pass) = serde_json::from_str::<Pass>(doc) else {
            return Ok(None);
        };
        let records = self.records.get_mut().map_err(poisoned)?;
        records.sync(std::mem::take(&mut pass.sync));
        let mut kit = Kit {
            scratch: self.scratch.get_mut().map_err(poisoned)?,
            walls: self.walls.get_mut().map_err(poisoned)?,
            views: self.views.get_mut().map_err(poisoned)?,
            regions: self.regions.get_mut().map_err(poisoned)?,
        };
        let answer = crate::kernel::route::pass(
            &mut self.inner,
            self.layers.get_mut().map_err(poisoned)?,
            self.tables.get_mut().map_err(poisoned)?,
            records,
            &mut kit,
            &pass,
        );
        Ok(Some(serde_json::to_string(&answer).map_err(err)?))
    }

    /// One native placement attempt after the sync, every write undone: the outcome as JSON.
    fn attempt(&mut self, doc: &str) -> PyResult<Option<String>> {
        let Ok(mut doc) = serde_json::from_str::<crate::kernel::attempt::Attempt>(doc) else {
            return Ok(None);
        };
        let records = self.records.get_mut().map_err(poisoned)?;
        records.sync(std::mem::take(&mut doc.sync));
        let mut kit = Kit {
            scratch: self.scratch.get_mut().map_err(poisoned)?,
            walls: self.walls.get_mut().map_err(poisoned)?,
            views: self.views.get_mut().map_err(poisoned)?,
            regions: self.regions.get_mut().map_err(poisoned)?,
        };
        let outcome = crate::kernel::attempt::attempt(
            &mut self.inner,
            self.layers.get_mut().map_err(poisoned)?,
            self.tables.get_mut().map_err(poisoned)?,
            records,
            &mut kit,
            &doc,
        );
        Ok(Some(serde_json::to_string(&outcome).map_err(err)?))
    }

    /// `World.admits` over the mirror after the sync, or None when the twin cannot answer.
    fn admits(&mut self, doc: &str) -> PyResult<Option<bool>> {
        let Ok(mut doc) = serde_json::from_str::<crate::kernel::attempt::Attempt>(doc) else {
            return Ok(None);
        };
        let records = self.records.get_mut().map_err(poisoned)?;
        records.sync(std::mem::take(&mut doc.sync));
        let kit = Kit {
            scratch: self.scratch.get_mut().map_err(poisoned)?,
            walls: self.walls.get_mut().map_err(poisoned)?,
            views: self.views.get_mut().map_err(poisoned)?,
            regions: self.regions.get_mut().map_err(poisoned)?,
        };
        Ok(crate::kernel::inspect::admits(
            &mut self.inner,
            self.layers.get_mut().map_err(poisoned)?,
            self.tables.get_mut().map_err(poisoned)?,
            records,
            &kit,
            &doc,
        )
        .ok())
    }

    /// Whether the regions were registered on this grid.
    fn has_regions(&self) -> PyResult<bool> {
        Ok(self
            .regions
            .lock()
            .map_err(|_| PyValueError::new_err("regions poisoned"))?
            .set)
    }
}

impl PyGrid {
    /// Run `f` over one query's prepared search.
    fn with_search<R>(
        &self,
        layer: &str,
        rules: &str,
        f: impl FnOnce(&Ask<'_>, &mut Scratch, &Tables) -> R,
    ) -> PyResult<R> {
        let query: Query = serde_json::from_str(rules).map_err(err)?;
        let tables = self.lock_tables()?;
        let carrier = {
            let mut views = self
                .views
                .lock()
                .map_err(|_| PyValueError::new_err("views cache poisoned"))?;
            let key = (query.carrier.clone(), tables.rules_version);
            match views.get(&key) {
                Some(view) => view.clone(),
                None => {
                    let view = Arc::new(CarrierView::new(&query.carrier, &tables));
                    views.retain(|k, _| k.1 == tables.rules_version);
                    views.insert(key, view.clone());
                    view
                }
            }
        };
        let (registered, unit_registered) = {
            let walls = self
                .walls
                .lock()
                .map_err(|_| PyValueError::new_err("walls cache poisoned"))?;
            let empty = || {
                let cells = (self.inner.width.max(0) * self.inner.height.max(0)) as usize;
                Arc::new(vec![false; cells])
            };
            (
                walls.get(&query.walls_key).cloned().unwrap_or_else(empty),
                walls
                    .get(&query.unit_walls_key)
                    .cloned()
                    .unwrap_or_else(empty),
            )
        };
        let view = View::new(
            query,
            self.inner.width,
            self.inner.height,
            registered,
            unit_registered,
            &tables,
        );
        let mut layers = self
            .layers
            .lock()
            .map_err(|_| PyValueError::new_err("layers cache poisoned"))?;
        let classified = layers.get(&self.inner, layer, &tables);
        let ask = Ask { view: &view, carrier: &carrier, tables: &tables, classified };
        let mut scratch = self
            .scratch
            .lock()
            .map_err(|_| PyValueError::new_err("scratch poisoned"))?;
        Ok(f(&ask, &mut scratch, &tables))
    }

    fn touch(&mut self, layer: &str, cells: &[(i64, i64)]) {
        let (w, h) = (self.inner.width, self.inner.height);
        if let Ok(layers) = self.layers.get_mut() {
            layers.touch(layer, cells, w, h);
        }
    }

    fn reset(&mut self) {
        if let Ok(layers) = self.layers.get_mut() {
            layers.reset();
        }
    }

    /// Note every cell a holder stands on as changed, after the tables' facts about it changed.
    fn touch_holder(&self, holder: &str) -> PyResult<()> {
        let mut layers = self
            .layers
            .lock()
            .map_err(|_| PyValueError::new_err("layers cache poisoned"))?;
        for (layer, cells) in self.inner.cells_of(holder) {
            layers.touch(&layer, &cells, self.inner.width, self.inner.height);
        }
        Ok(())
    }

    fn lock_tables(&self) -> PyResult<std::sync::MutexGuard<'_, Tables>> {
        self.tables
            .lock()
            .map_err(|_| PyValueError::new_err("tables poisoned"))
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
